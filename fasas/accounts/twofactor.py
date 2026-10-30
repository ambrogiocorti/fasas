"""
Verifica in due passaggi: dopo la password serve un codice di 6 cifre generato dall'app sul telefono
(Google Authenticator, Microsoft Authenticator, FreeOTP…), secondo lo standard TOTP (RFC 6238).

- Obbligatoria per i ruoli in FASAS_2FA_REQUIRED_ROLES (di default amministratore, coordinatore, medico).
- Con FASAS_2FA_TRUSTED_NETWORKS impostata, obbligatoria per tutti quando l'accesso arriva da fuori rete;
  la prima attivazione si fa solo dalla rete della struttura, così una password rubata non basta ad attivarla.
- Il segreto è cifrato nel database con le chiavi dei documenti; ogni codice vale una sola volta.
- Dieci codici di recupero monouso per quando il telefono non è disponibile (salvati solo come impronta).
"""
import base64
import hashlib
import hmac
import ipaddress
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from fasas.core import encryption
from fasas.core.middleware import client_ip

STEP = 30
DIGITS = 6
WINDOW = 1  # un passo prima e dopo: tollera 30 secondi di scarto tra l'orologio del telefono e il server
RECOVERY_CODES = 10
SESSION_PENDING = "fasas_2fa_pending"
SESSION_SETUP = "fasas_2fa_setup"
PENDING_SECONDS = 300
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret):
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret, step):
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def current_step(now=None):
    return int((time.time() if now is None else now) // STEP)


def matching_step(secret, code, now=None):
    """Passo temporale a cui corrisponde il codice, o None."""
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(digits) != DIGITS:
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, candidate), digits):
            return candidate
    return None


def provisioning_uri(secret, account):
    issuer = settings.FASAS_2FA_ISSUER
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"


def qr_svg(uri):
    """QR code in SVG da mostrare all'attivazione; vuoto se manca la libreria (si inserisce il codice a mano)."""
    try:
        import segno
    except ImportError:  # pragma: no cover
        return ""
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#111", light="#fff", omitsize=False)


def encrypt_secret(secret):
    return encryption.encrypt(secret.encode())


def decrypt_secret(token):
    return encryption.decrypt(bytes(token)).decode()


def _hash_recovery(code):
    normalized = "".join(ch for ch in code.lower() if ch.isalnum())
    return hashlib.sha256(f"fasas-recovery:{normalized}".encode()).hexdigest()


def _new_recovery_code():
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


# --- Regole -------------------------------------------------------------------------------------------

def _trusted_networks():
    return [ipaddress.ip_network(net, strict=False) for net in settings.FASAS_2FA_TRUSTED_NETWORKS]


def from_trusted_network(request):
    """Vero se le reti della struttura non sono configurate o se la richiesta arriva da una di esse."""
    networks = _trusted_networks()
    if not networks:
        return True
    try:
        ip = ipaddress.ip_address(client_ip(request))
    except ValueError:
        return False
    return any(ip in net for net in networks)


def role_requires(user):
    return user.role in settings.FASAS_2FA_REQUIRED_ROLES or (user.is_superuser and bool(settings.FASAS_2FA_REQUIRED_ROLES))


def is_enrolled(user):
    from .models import TwoFactorDevice

    return TwoFactorDevice.objects.filter(user=user).exists()


def requirement(user, request):
    """
    Cosa serve dopo la password:
    - "none": accesso diretto;
    - "verify": codice dall'app (utente già attivato);
    - "setup": attivazione obbligatoria adesso;
    - "refused": serve la verifica ma qui non si può attivare (fuori dalla rete della struttura).
    """
    if is_enrolled(user):
        return "verify"
    needed = role_requires(user) or not from_trusted_network(request)
    if not needed:
        return "none"
    return "setup" if from_trusted_network(request) else "refused"


# --- Operazioni ---------------------------------------------------------------------------------------

def verify(user, code):
    """Controlla un codice dell'app o un codice di recupero. Restituisce "totp", "recovery" o None."""
    from .models import RecoveryCode, TwoFactorDevice

    with transaction.atomic():
        device = TwoFactorDevice.objects.select_for_update().filter(user=user).first()
        if device is None:
            return None
        step = matching_step(decrypt_secret(device.secret), code)
        if step is not None:
            if step <= device.last_step:  # lo stesso codice non vale due volte
                return None
            device.last_step = step
            device.last_used_at = timezone.now()
            device.save(update_fields=["last_step", "last_used_at"])
            return "totp"
        if code and len("".join(ch for ch in str(code) if ch.isalnum())) == 10:
            used = RecoveryCode.objects.filter(user=user, code_hash=_hash_recovery(str(code)),
                                               used_at__isnull=True).update(used_at=timezone.now())
            if used:
                return "recovery"
    return None


def regenerate_recovery_codes(user):
    """Nuovi codici di recupero (i precedenti non valgono più). Il testo si mostra una volta sola."""
    from .models import RecoveryCode

    codes = [_new_recovery_code() for _ in range(RECOVERY_CODES)]
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create([RecoveryCode(user=user, code_hash=_hash_recovery(c)) for c in codes])
    return codes


def enroll(user, secret, code):
    """Attiva la verifica se il codice dell'app è giusto. Restituisce i codici di recupero, o None."""
    from fasas.audit.models import AuditLog
    from fasas.audit.services import log_event

    from .models import TwoFactorDevice

    step = matching_step(secret, code)
    if step is None:
        return None
    with transaction.atomic():
        TwoFactorDevice.objects.filter(user=user).delete()
        TwoFactorDevice.objects.create(user=user, secret=encrypt_secret(secret), last_step=step)
        codes = regenerate_recovery_codes(user)
        log_event(AuditLog.Action.PERMISSION, user, user=user,
                  changes={"verifica_in_due_passaggi": ["non attiva", "attivata"]})
    return codes


def disable(user, by):
    """Toglie la verifica (reimpostazione da parte dell'amministratore o disattivazione volontaria)."""
    from fasas.audit.models import AuditLog
    from fasas.audit.services import log_event

    from .models import RecoveryCode, TwoFactorDevice

    with transaction.atomic():
        removed, _ = TwoFactorDevice.objects.filter(user=user).delete()
        RecoveryCode.objects.filter(user=user).delete()
        if removed:
            log_event(AuditLog.Action.PERMISSION, user, user=by,
                      changes={"verifica_in_due_passaggi": ["attiva", "reimpostata" if by != user else "disattivata"]})
    return bool(removed)


def recovery_codes_left(user):
    return user.recovery_codes.filter(used_at__isnull=True).count()


# --- Accesso in attesa del secondo passaggio ------------------------------------------------------------

def start_pending(request, user, next_url):
    request.session[SESSION_PENDING] = {
        "user": user.pk, "backend": getattr(user, "backend", "django.contrib.auth.backends.ModelBackend"),
        "at": int(time.time()), "next": next_url,
    }


def pending_user(request):
    from .models import User

    data = request.session.get(SESSION_PENDING)
    if not data or time.time() - data.get("at", 0) > PENDING_SECONDS:
        request.session.pop(SESSION_PENDING, None)
        return None, None
    user = User.objects.filter(pk=data["user"], is_active=True).first()
    if user is not None:
        user.backend = data["backend"]
    return user, data.get("next") or ""


def clear_pending(request):
    request.session.pop(SESSION_PENDING, None)
    request.session.pop(SESSION_SETUP, None)
