"""
Firma con CIE (FASAS Sign): abbinamento dei dispositivi e ciclo di vita delle richieste di firma.

Il FASAS Signer (computer con lettore NFC e Software CIE, o in futuro l'app per telefono) contatta il
server in uscita: non apre porte locali, quindi una pagina web non può pilotarlo (niente CSRF né richieste
cross-origin verso localhost). Ogni dispositivo si autentica con un token di cui il server conserva solo
l'impronta, ogni passo della richiesta richiede il nonce del passo corrente e ogni richiesta scade dopo
pochi minuti. Il PIN viene digitato sul dispositivo e va solo alla carta.

Il firmatario è l'utente collegato al FASAS: il codice fiscale nel certificato della carta deve coincidere
con quello del suo profilo, altrimenti la firma viene rifiutata e il tentativo registrato nell'audit.
"""
import datetime
import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import delete_stored, read_encrypted, store_encrypted

from . import external
from . import nis as nis_protocol
from .models import CieAccess, CieEnrollment, DevicePairing, LegalLevel, Signature, SignatureRequest, SignerDevice
from .providers import SignatureError, next_field_name, timestamper

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza 0/O e 1/I, facili da confondere
Status = SignatureRequest.Status
PERMISSION = "signatures.sign_with_cie"

# Errori che il dispositivo può segnalare: si registra solo il codice, mai testo libero (niente dati nei log)
DEVICE_ERRORS = {
    "card_absent": "Nessuna CIE rilevata sul lettore.",
    "card_removed": "La carta è stata allontanata dal lettore durante la firma: riprovare tenendola ferma.",
    "reader_missing": "Nessun lettore di smart card o NFC collegato al computer.",
    "middleware_missing": "Il Software CIE (middleware del Ministero dell'Interno) non è installato o non è stato trovato.",
    "card_not_enrolled": "La CIE non è abbinata al Software CIE di questo computer: abbinarla dall'app «CIE ID».",
    "pin_wrong": "PIN errato.",
    "pin_blocked": "PIN della CIE bloccato: sbloccarlo con il PUK dall'app «CIE ID».",
    "cancelled": "Firma annullata sul dispositivo.",
    "cert_missing": "Sulla carta non è stato trovato il certificato.",
    "not_cie": "La carta appoggiata al telefono non è una CIE.",
    "nfc_unsupported": "Il telefono non supporta i comandi NFC necessari alla CIE: usare un altro telefono o il computer.",
    "unsupported_mechanism": "La carta non supporta il meccanismo di firma RSA richiesto.",
    "timeout": "Tempo scaduto sul dispositivo.",
    "device_error": "Errore del dispositivo di firma.",
}
# Esiti che indicano un uso improprio: oltre al fallimento si registra un «tentativo non autorizzato»
SECURITY_CODES = {"not_found", "wrong_device", "bad_nonce", "cert_mismatch", "bad_signature", "bad_state",
                  "pairing_invalid", "version_changed", "forbidden"}
DEVICE_STATES = {"card_missing", "card", "pin_wrong", "signing"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _code(length=4):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def _normalize(code):
    return "".join(ch for ch in (code or "").upper() if ch in ALPHABET)


def is_enabled():
    return settings.FASAS_CIE_ENABLED


def can_sign(user):
    return is_enabled() and user.is_active and user.has_perm(PERMISSION)


def documents_gate_on():
    """La struttura chiede la verifica con CIE per aprire, scaricare o modificare i documenti."""
    from fasas.core.models import SystemConfig

    return SystemConfig.get().documents_cie_required


def can_use_device(user):
    """Può abbinare e usare un FASAS Signer: per firmare con la CIE oppure per aprire i documenti verificandosi."""
    if not (is_enabled() and user.is_active):
        return False
    return user.has_perm(PERMISSION) or (documents_gate_on() and user.has_perm("documents.view_document"))


def deny(reason, *, user=None, obj=None, request_id="", code=""):
    """Tentativo non autorizzato o anomalo: resta nell'audit (catena SHA-256, rileva manomissioni)."""
    log_event(AuditLog.Action.DENIED, obj, user=user, repr_text=f"Firma CIE {request_id}"[:255] if obj is None else None,
              changes={"esito": [None, "rifiutato"], "codice": [None, code]}, reason=reason)


# --- Abbinamento dei dispositivi ---------------------------------------------------------------------------

@transaction.atomic
def create_pairing(user):
    if not can_use_device(user):
        raise SignatureError("Non hai il permesso di usare la CIE nel FASAS.", "forbidden")
    now = timezone.now()
    DevicePairing.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).update(expires_at=now)
    code = f"{_code()}-{_code()}"
    DevicePairing.objects.create(user=user, code_hash=_hash(_normalize(code)),
                                 expires_at=now + datetime.timedelta(minutes=settings.FASAS_CIE_PAIRING_MINUTES))
    log_event(AuditLog.Action.CONFIG, None, user=user, repr_text="Abbinamento FASAS Signer",
              changes={"codice di abbinamento": [None, "generato"]})
    return code


def pair_device(code, name, platform, app_version=""):
    """Restituisce (dispositivo, token). Il token si mostra una sola volta al dispositivo; qui se ne salva l'impronta."""
    now = timezone.now()
    with transaction.atomic():
        pairing = (DevicePairing.objects.select_for_update().select_related("user")
                   .filter(code_hash=_hash(_normalize(code)), used_at__isnull=True, expires_at__gt=now).first())
        if pairing is None or not can_use_device(pairing.user):
            raise SignatureError("Codice di abbinamento non valido o scaduto.", "pairing_invalid")
        token = secrets.token_urlsafe(32)
        if platform not in SignerDevice.Platform.values:
            platform = SignerDevice.Platform.OTHER
        device = SignerDevice.objects.create(
            user=pairing.user, name=(name or "FASAS Signer").strip()[:100], platform=platform,
            app_version=(app_version or "")[:30], token_hash=_hash(token), last_seen_at=now,
        )
        pairing.used_at = now
        pairing.device = device
        pairing.save(update_fields=["used_at", "device"])
    return device, token


def authenticate_device(token):
    if not token:
        return None
    device = (SignerDevice.objects.select_related("user")
              .filter(token_hash=_hash(token), revoked_at__isnull=True).first())
    if device is None or not can_use_device(device.user):
        return None
    now = timezone.now()
    if device.last_seen_at is None or now - device.last_seen_at > datetime.timedelta(seconds=15):
        SignerDevice.objects.filter(pk=device.pk).update(last_seen_at=now)
        device.last_seen_at = now
    return device


def update_device_status(device, status):
    """Stato dei componenti riportato dal Signer: middleware, lettori, carta. Solo campi noti, nessun dato personale."""
    allowed = {"middleware": str, "middleware_path": str, "middleware_found": bool, "readers": list,
               "card_present": bool, "os": str, "app_version": str, "mechanisms": list, "nfc": str}
    clean = {}
    for key, kind in allowed.items():
        value = status.get(key)
        if isinstance(value, kind):
            clean[key] = [str(v)[:80] for v in value[:8]] if kind is list else (value[:200] if kind is str else value)
    device.status = clean
    device.status_at = timezone.now()
    fields = ["status", "status_at"]
    if clean.get("app_version"):
        device.app_version = clean["app_version"][:30]
        fields.append("app_version")
    device.save(update_fields=fields)
    return clean


@transaction.atomic
def revoke_device(device, by):
    if device.user_id != by.pk and not by.has_perm("signatures.manage_signer_devices"):
        raise SignatureError("Non puoi revocare questo dispositivo.", "forbidden")
    device.revoked_at = timezone.now()
    device.save(update_fields=["revoked_at"])
    for request in SignatureRequest.objects.select_for_update().filter(device=device,
                                                                       status__in=SignatureRequest.CANCELLABLE):
        _close(request, Status.CANCELLED, "device_revoked", "Dispositivo di firma revocato.")


# --- Richieste di firma (lato FASAS web) -------------------------------------------------------------------

def test_pdf(user):
    """PDF di prova senza dati sanitari, per collaudare lettore, carta e catena di verifica."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("Prova di firma con CIE")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, 760, "FASAS Sign – prova di firma con CIE")
    pdf.setFont("Helvetica", 11)
    lines = [
        f"Data e ora: {timezone.localtime():%d/%m/%Y %H:%M}",
        "Documento di prova: non contiene dati sanitari né dati di ospiti.",
        "Serve solo a verificare lettore, carta, Software CIE e verifica della firma.",
    ]
    for offset, line in enumerate(lines):
        pdf.drawString(72, 730 - offset * 18, line)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _base_request(user, *, reason="", location="", previous=None, **fields):
    now = timezone.now()
    with_timestamp = settings.FASAS_CIE_TIMESTAMP and timestamper() is not None
    return SignatureRequest(
        user=user, reason=(reason or "")[:255], location=(location or "")[:255], verify_code=f"{_code()}-{_code()}",
        nonce_hash=_hash(secrets.token_urlsafe(24)), created_at=now, updated_at=now,
        expires_at=now + datetime.timedelta(minutes=settings.FASAS_CIE_REQUEST_MINUTES),
        with_timestamp=with_timestamp, previous=previous, attempt=(previous.attempt + 1) if previous else 1, **fields,
    )


def create_request(version, user, reason="", previous=None):
    """Blocca la versione e crea la richiesta. Se l'utente ha già una richiesta attiva per la versione, la restituisce."""
    from fasas.documents.services import read_version
    from fasas.guests.services import ensure_not_archived

    if not can_sign(user):
        raise SignatureError("Non hai il permesso di firmare con la CIE.", "forbidden")
    if not version.is_pdf:
        raise SignatureError("Con la CIE si firmano solo documenti PDF (formato PAdES).")
    document = version.document
    ensure_not_archived(document.guest)
    if document.current_version.pk != version.pk:
        raise SignatureError("Si può firmare solo l'ultima versione del documento.", "version_changed")
    if not external.trust_roots():
        raise SignatureError("Firma con CIE non ancora attivabile: l'amministratore deve configurare le CA della CIE "
                             "(FASAS_CIE_TRUST_ROOTS).", "trust_not_configured")
    if settings.FASAS_FEA_REQUIRE_ACCEPTANCE and valid_acceptance(user) is None:
        raise SignatureError("Prima della prima firma con CIE devi accettare le condizioni della firma elettronica "
                             "avanzata, firmandole con la tua CIE (Impostazioni › Firma digitale).", "acceptance_required")
    existing = SignatureRequest.objects.filter(version=version, status__in=SignatureRequest.ACTIVE).first()
    if existing is not None:
        expire_if_needed(existing)
        if existing.is_active:
            if existing.user_id == user.pk:
                return existing
            raise SignatureError(f"Il documento è già in firma da parte di {existing.user}.", "locked")
    read_version(version, user=user, audit=False)  # verifica l'integrità prima di bloccare la versione
    request = _base_request(user, reason=reason, location=str(document.guest.community), previous=previous,
                            purpose=SignatureRequest.Purpose.DOCUMENT, version=version, version_sha256=version.sha256)
    try:
        with transaction.atomic():
            request.save()
    except IntegrityError as exc:  # richiesta concorrente sulla stessa versione
        raise SignatureError("Il documento è già in firma.", "locked") from exc
    return request


def create_test_request(user):
    if not can_sign(user):
        raise SignatureError("Non hai il permesso di firmare con la CIE.", "forbidden")
    pdf = test_pdf(user)
    request = _base_request(user, reason="Prova di funzionamento", location="FASAS",
                            purpose=SignatureRequest.Purpose.TEST, version_sha256=hashlib.sha256(pdf).hexdigest())
    request.result_storage = store_encrypted(pdf, "signing/tests")  # originale; a firma riuscita, il firmato
    request.save()
    return request


def valid_acceptance(user):
    from .models import FEAAcceptance

    return FEAAcceptance.objects.filter(user=user, revoked_at__isnull=True).first()


def create_acceptance_request(user):
    """Dichiarazione di accettazione delle condizioni della FEA, da firmare con la CIE (identifica il firmatario)."""
    from .fea_terms import acceptance_pdf

    if not can_sign(user):
        raise SignatureError("Non hai il permesso di firmare con la CIE.", "forbidden")
    if not external.trust_roots():
        raise SignatureError("Firma con CIE non ancora attivabile: l'amministratore deve configurare le CA della CIE "
                             "(FASAS_CIE_TRUST_ROOTS).", "trust_not_configured")
    if not user.fiscal_code:
        raise SignatureError("Nel tuo profilo manca il codice fiscale: chiedilo all'amministratore.", "missing_fiscal_code")
    pdf = acceptance_pdf(user)
    request = _base_request(user, reason="Accettazione delle condizioni della firma elettronica avanzata con CIE",
                            location=str(_community()), purpose=SignatureRequest.Purpose.ACCEPTANCE,
                            version_sha256=hashlib.sha256(pdf).hexdigest())
    request.result_storage = store_encrypted(pdf, "signing/acceptances")
    request.save()
    return request


def access_methods():
    """Metodi ammessi per aprire i documenti: CIE + PIN FASAS (NIS) e/o CIE con il suo PIN."""
    from fasas.core.models import SystemConfig

    return ["nis", "cie"] if SystemConfig.get().documents_verification == "nis" else ["cie"]


def enrollment_of(user):
    return CieEnrollment.objects.filter(user=user, revoked_at__isnull=True).first()


def create_access_request(user, guest, document=None, method="cie"):
    """
    Verifica di identità con la CIE prima di aprire, scaricare o modificare un documento (o, senza documento, tutti
    i documenti dell'ospite per l'esportazione della cartella). La carta firma una sfida casuale del server: non è
    la firma di un documento e non ne crea una nuova versione.
    """
    if not can_use_device(user) or not user.has_perm("documents.view_document"):
        raise SignatureError("Non puoi usare la CIE per aprire i documenti: chiedi all'amministratore.", "forbidden")
    if method not in access_methods():
        raise SignatureError("Metodo di verifica non ammesso dalla configurazione.", "forbidden")
    if method == "nis":
        enrollment = enrollment_of(user)
        if enrollment is None:
            raise SignatureError("Prima registra la tua CIE e scegli il PIN FASAS (Impostazioni › Firma digitale).",
                                 "not_enrolled")
        if not enrollment.is_confirmed:
            raise SignatureError("La registrazione della tua CIE aspetta la conferma dell'amministratore.",
                                 "not_confirmed")
        if not enrollment.pin_hash:
            raise SignatureError("Scegli il PIN FASAS in Impostazioni › Firma digitale.", "pin_missing")
        if enrollment.pin_locked:
            raise SignatureError("PIN FASAS bloccato dopo troppi errori: chiedi all'amministratore di azzerare la "
                                 "registrazione della CIE e registrala di nuovo.", "pin_blocked")
    else:
        if not external.trust_roots():
            raise SignatureError("Verifica con CIE non ancora attivabile: l'amministratore deve configurare le CA della "
                                 "CIE (FASAS_CIE_TRUST_ROOTS).", "trust_not_configured")
        if not user.fiscal_code:
            raise SignatureError("Nel tuo profilo manca il codice fiscale: chiedilo all'amministratore.",
                                 "missing_fiscal_code")
    existing = SignatureRequest.objects.filter(
        user=user, purpose=SignatureRequest.Purpose.ACCESS, access_guest=guest, access_document=document,
        access_method=method, status__in=SignatureRequest.ACTIVE).first()
    if existing is not None and expire_if_needed(existing).is_active:
        return existing
    request = _base_request(user, reason="Verifica di identità per aprire i documenti", location=str(_community()),
                            purpose=SignatureRequest.Purpose.ACCESS, access_guest=guest, access_document=document,
                            access_method=method, version_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest())
    request.with_timestamp = False
    request.save()
    return request


def _access_challenge(request):
    """Ciò che la carta firma per dimostrare l'identità: legato a richiesta, utente e documento, mai riusabile."""
    text = "\n".join([
        "FASAS - verifica di identita' con CIE (non e' la firma di un documento)",
        f"richiesta={request.pk}", f"codice={request.verify_code}", f"utente={request.user.username}",
        f"ospite={request.access_guest_id}", f"documento={request.access_document_id or 'tutti'}",
        f"quando={timezone.now().isoformat()}", f"casuale={secrets.token_hex(16)}",
    ]).encode()
    return external.PreparedSignature(field_name="", document_digest="", reserved_start=0, reserved_end=0,
                                      signed_attrs=external.b64(text))


def _grant_access(request_id):
    from fasas.core.models import SystemConfig

    with transaction.atomic():
        request = SignatureRequest.objects.select_for_update().get(pk=request_id)
        if request.status != Status.VERIFYING:
            raise SignatureError("Richiesta chiusa durante la verifica.", "bad_state")
        now = timezone.now()
        by_nis = request.access_method == "nis"
        access = CieAccess.objects.create(
            user=request.user, guest=request.access_guest, document=request.access_document, request=request,
            granted_at=now, certificate_subject=request.certificate_subject, method="nis" if by_nis else "cie",
            expires_at=now + datetime.timedelta(minutes=SystemConfig.get().documents_cie_minutes),
        )
        request.verification = {**request.verification, "identity_verified": True, "level": "Verifica di identità"}
        log_event(AuditLog.Action.PERMISSION, access, user=request.user, guest=request.access_guest,
                  repr_text="Accesso ai documenti verificato con CIE",
                  changes={"verifica": [None, "CIE + PIN FASAS" if by_nis
                                        else "CIE" if not request.is_test_card else "carta di prova"],
                           "documento": [None, str(request.access_document_id or "tutti")],
                           "valido_fino": [None, timezone.localtime(access.expires_at).strftime("%d/%m/%Y %H:%M")]})
        _close(request, Status.SIGNED)
    return request


def create_enroll_request(user):
    """Primo accesso: si registra la propria CIE appoggiandola al telefono (non serve il PIN della carta)."""
    if not can_use_device(user):
        raise SignatureError("Non puoi usare la CIE nel FASAS: chiedi all'amministratore.", "forbidden")
    if not nis_protocol.csca_certificates():
        raise SignatureError("Registrazione non ancora attivabile: l'amministratore deve configurare i certificati "
                             "della CSCA italiana (FASAS_CIE_CSCA).", "trust_not_configured")
    existing = SignatureRequest.objects.filter(user=user, purpose=SignatureRequest.Purpose.ENROLL,
                                               status__in=SignatureRequest.ACTIVE).first()
    if existing is not None and expire_if_needed(existing).is_active:
        return existing
    request = _base_request(user, reason="Registrazione della CIE", location=str(_community()),
                            purpose=SignatureRequest.Purpose.ENROLL, access_method="nis",
                            version_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest())
    request.with_timestamp = False
    request.save()
    return request


def _card_data(data, field, required=True):
    value = data.get(field) or ""
    if not value and not required:
        return None
    raw = external.unb64(value, "Dati della carta")
    if not raw or len(raw) > 16384:
        raise SignatureError("Dati della carta non validi.", "card_data")
    return raw


def _check_pin(enrollment, pin):
    """PIN FASAS: impronta come le password; dopo 5 errori di seguito la registrazione si blocca."""
    from django.contrib.auth.hashers import check_password

    if enrollment.pin_locked:
        raise SignatureError("PIN FASAS bloccato dopo troppi errori: chiedi all'amministratore.", "pin_blocked")
    if pin and check_password(str(pin), enrollment.pin_hash):
        if enrollment.pin_failures:
            CieEnrollment.objects.filter(pk=enrollment.pk).update(pin_failures=0)
        return
    with transaction.atomic():  # l'errore resta registrato anche se poi la richiesta fallisce
        locked = CieEnrollment.objects.select_for_update().get(pk=enrollment.pk)
        locked.pin_failures += 1
        locked.save(update_fields=["pin_failures"])
    left = max(0, CieEnrollment.MAX_PIN_FAILURES - locked.pin_failures)
    if left == 0:
        log_event(AuditLog.Action.DENIED, locked, user=enrollment.user, repr_text="PIN FASAS bloccato",
                  changes={"pin_fasas": [None, "bloccato dopo 5 errori"]})
        raise SignatureError("PIN FASAS bloccato dopo troppi errori: chiedi all'amministratore.", "pin_blocked")
    raise SignatureError(f"PIN FASAS errato. Tentativi rimasti: {left}.", "pin_wrong")


def submit_nis(request_id, device, nonce, data):
    """
    Il telefono ha letto dalla carta NIS, chiave pubblica (e, alla registrazione, il SOD) e ha fatto firmare alla
    carta la sfida del server. Registrazione: si verificano firma del Ministero e originalità, poi si salva la carta.
    Accesso: stessa carta registrata, autenticazione interna valida e PIN FASAS corretto.
    """
    with transaction.atomic():
        request = _locked(request_id, device, nonce, states=(Status.AUTHORIZING,))
    if request.access_method != "nis":
        raise SignatureError("Richiesta non prevista per la CIE senza PIN.", "bad_state")
    nis_raw, kpub = _card_data(data, "nis"), _card_data(data, "kpub")
    response = _card_data(data, "response")
    challenge = external.unb64(request.prepared.get("challenge", ""))
    enrollment = None
    try:
        if request.purpose == SignatureRequest.Purpose.ENROLL:
            sod = _card_data(data, "sod")
            info = nis_protocol.verify_sod(sod, nis_raw, kpub)
            nis_protocol.verify_internal_auth(kpub, challenge, response)
        else:
            enrollment = enrollment_of(request.user)
            if enrollment is None or not enrollment.is_confirmed:
                raise SignatureError("La tua CIE non è registrata o non è ancora confermata.", "not_enrolled")
            if (nis_protocol.nis_hash(nis_raw) != enrollment.nis_hash
                    or nis_protocol.kpub_hash(kpub) != enrollment.kpub_hash):
                raise SignatureError("Questa non è la CIE registrata per il tuo utente.", "cert_mismatch")
            nis_protocol.verify_internal_auth(kpub, challenge, response)
    except SignatureError as exc:
        fail(request.pk, exc.code, str(exc))
        raise
    if enrollment is not None:
        try:
            _check_pin(enrollment, data.get("pin"))
        except SignatureError as exc:
            if exc.code != "pin_wrong":
                fail(request.pk, exc.code, str(exc))
                raise
            # PIN errato: la richiesta resta aperta per riprovare (stessa carta, stesso passo)
            left = max(0, CieEnrollment.MAX_PIN_FAILURES - CieEnrollment.objects.get(pk=enrollment.pk).pin_failures)
            SignatureRequest.objects.filter(pk=request.pk).update(
                error_code="pin_wrong", error_message="PIN FASAS errato.", pin_attempts_left=left)
            exc.attempts_left = left
            raise
    with transaction.atomic():
        request = _locked(request_id, device, nonce, states=(Status.AUTHORIZING,))
        request.status, request.error_code, request.error_message = Status.VERIFYING, "", ""
        _rotate_nonce(request)  # la risposta della carta si accetta una sola volta
        request.save()
    if request.purpose == SignatureRequest.Purpose.ENROLL:
        return _save_enrollment(request.pk, nis_raw, kpub, info)
    return _grant_access(request.pk)


def _save_enrollment(request_id, nis_raw, kpub, info):
    nis_digest = nis_protocol.nis_hash(nis_raw)
    with transaction.atomic():
        request = SignatureRequest.objects.select_for_update().get(pk=request_id)
        if CieEnrollment.objects.filter(nis_hash=nis_digest, revoked_at__isnull=True).exclude(user=request.user).exists():
            message = ("Questa CIE è già registrata per un altro utente del FASAS (una carta vale per una sola persona). "
                       "Se è la tua, chiedi all'amministratore di azzerare quella registrazione in Utenti e permessi.")
            _close(request, Status.FAILED, "card_in_use", message[:255])
            raise SignatureError(message, "card_in_use")
        current = CieEnrollment.objects.filter(user=request.user, revoked_at__isnull=True).first()
        if current is not None and current.nis_hash == nis_digest and current.kpub_hash == nis_protocol.kpub_hash(kpub):
            # stessa carta già registrata (es. app reinstallata): restano PIN FASAS e conferma dell'amministratore
            request.verification = {**request.verification, "enrolled": True, "level": "CIE già registrata"}
            log_event(AuditLog.Action.CONFIG, current, user=request.user, repr_text="Registrazione della CIE",
                      changes={"cie": ["registrata", "stessa carta verificata di nuovo"]})
            _close(request, Status.SIGNED)
            return request
        now = timezone.now()
        CieEnrollment.objects.filter(user=request.user, revoked_at__isnull=True).update(
            revoked_at=now, revoked_reason="Sostituita da una nuova registrazione")
        enrollment = CieEnrollment.objects.create(
            user=request.user, nis_hash=nis_digest, kpub=external.b64(nis_protocol.first_tlv(kpub)),
            kpub_hash=nis_protocol.kpub_hash(kpub), document_signer=info["document_signer"], request=request,
            enrolled_at=now)
        request.verification = {**request.verification, "enrolled": True, "level": "CIE registrata"}
        log_event(AuditLog.Action.CONFIG, enrollment, user=request.user, repr_text="Registrazione della CIE",
                  changes={"cie": [None, "registrata, da confermare"], "document_signer": [None, info["csca"]]})
        _close(request, Status.SIGNED)
    return request


def set_fasas_pin(enrollment, pin, by):
    from django.contrib.auth.hashers import make_password

    enrollment.pin_hash, enrollment.pin_set_at, enrollment.pin_failures = make_password(pin), timezone.now(), 0
    enrollment.save(update_fields=["pin_hash", "pin_set_at", "pin_failures"])
    log_event(AuditLog.Action.CONFIG, enrollment, user=by, repr_text="PIN FASAS",
              changes={"pin_fasas": [None, "impostato"]})


def confirm_enrollment(enrollment, by):
    if by.pk == enrollment.user_id:
        raise SignatureError("La registrazione della propria CIE la conferma un altro amministratore.", "forbidden")
    enrollment.confirmed_at, enrollment.confirmed_by = timezone.now(), by
    enrollment.save(update_fields=["confirmed_at", "confirmed_by"])
    log_event(AuditLog.Action.PERMISSION, enrollment, user=by, repr_text=f"CIE di {enrollment.user} confermata",
              changes={"cie": ["da confermare", "confermata (carta e persona viste)"]})


def revoke_enrollment(enrollment, by, reason):
    enrollment.revoked_at, enrollment.revoked_reason = timezone.now(), (reason or "Azzerata")[:255]
    enrollment.save(update_fields=["revoked_at", "revoked_reason"])
    log_event(AuditLog.Action.PERMISSION, enrollment, user=by, repr_text=f"CIE di {enrollment.user} azzerata",
              changes={"cie": ["registrata", "azzerata"]}, reason=enrollment.revoked_reason)


def has_document_access(user, guest, document=None):
    """Con la verifica attiva serve un accesso CIE valido per quel documento (o per tutti i documenti dell'ospite)."""
    if not documents_gate_on():
        return True
    scope = Q(document__isnull=True) if document is None else (Q(document=document) | Q(document__isnull=True))
    return CieAccess.objects.filter(scope, user=user, guest=guest, expires_at__gt=timezone.now()).exists()


def revoke_acceptance(acceptance, by, reason=""):
    acceptance.revoked_at, acceptance.revoked_reason = timezone.now(), (reason or "Revocata dal firmatario")[:255]
    acceptance.save(update_fields=["revoked_at", "revoked_reason"])
    log_event(AuditLog.Action.PERMISSION, acceptance, user=by,
              changes={"accettazione_FEA": ["valida", "revocata"]}, reason=acceptance.revoked_reason)


def _community():
    from fasas.core.models import Community

    return Community.default()


def _close(request, status, code="", message=""):
    request.status = status
    request.error_code = code[:40]
    request.error_message = message[:255]
    request.completed_at = request.updated_at = timezone.now()
    request.nonce_hash = _hash(secrets.token_urlsafe(24))  # nessun passo successivo è più accettato
    if request.prepared_storage:
        delete_stored(request.prepared_storage)
        request.prepared_storage = ""
    request.save()


def expire_if_needed(request):
    if not request.is_active:
        return request
    grace = datetime.timedelta(minutes=2) if request.status == Status.VERIFYING else datetime.timedelta()
    if timezone.now() > request.expires_at + grace:
        with transaction.atomic():
            locked = SignatureRequest.objects.select_for_update().get(pk=request.pk)
            if locked.is_active:
                _close(locked, Status.EXPIRED, "expired", "Tempo scaduto: avviare una nuova firma.")
        request.refresh_from_db()
    return request


def cancel_request(request, user):
    if request.user_id != user.pk:
        raise SignatureError("Richiesta non trovata.", "not_found")
    with transaction.atomic():
        locked = SignatureRequest.objects.select_for_update().get(pk=request.pk)
        if locked.status not in SignatureRequest.CANCELLABLE:
            raise SignatureError("La richiesta non si può più annullare.", "bad_state")
        _close(locked, Status.CANCELLED, "cancelled_by_user", "Annullata dall'utente.")
    return locked


def retry_request(request, user):
    """Nuovo tentativo dopo errore, annullamento o scadenza: nuova richiesta (nuovo id e nonce), mai riuso della vecchia."""
    if request.user_id != user.pk:
        raise SignatureError("Richiesta non trovata.", "not_found")
    expire_if_needed(request)
    if request.is_active or request.status == Status.SIGNED:
        raise SignatureError("Questa richiesta non richiede un nuovo tentativo.", "bad_state")
    following = SignatureRequest.objects.filter(previous=request).first()
    if following is not None:
        if following.is_active:
            return following
        raise SignatureError("Per questa richiesta è già stato fatto un nuovo tentativo.", "bad_state")
    if request.purpose == SignatureRequest.Purpose.ACCESS:
        new = create_access_request(user, request.access_guest, request.access_document,
                                    request.access_method or "cie")
        if new.pk != request.pk and new.previous_id is None:
            new.previous, new.attempt = request, request.attempt + 1
            new.save(update_fields=["previous", "attempt"])
        return new
    if request.purpose in (SignatureRequest.Purpose.TEST, SignatureRequest.Purpose.ACCEPTANCE):
        new = (create_test_request if request.purpose == SignatureRequest.Purpose.TEST
               else create_acceptance_request)(user)
        new.previous, new.attempt = request, request.attempt + 1
        new.save(update_fields=["previous", "attempt"])
        return new
    return create_request(request.version, user, request.reason, previous=request)


def cleanup_stale():
    """Job: chiude le richieste scadute e cancella i PDF preparati rimasti."""
    count = 0
    for request in SignatureRequest.objects.filter(status__in=SignatureRequest.ACTIVE, expires_at__lt=timezone.now()):
        expire_if_needed(request)
        count += 1
    return {"expired": count}


# --- Passi eseguiti dal dispositivo ------------------------------------------------------------------------

def pending_for(device):
    now = timezone.now()
    pending = (SignatureRequest.objects.select_related("version__document", "access_document", "access_guest")
               .filter(user=device.user, status=Status.WAITING, expires_at__gt=now)
               .filter(Q(device__isnull=True) | Q(device=device)).order_by("created_at"))
    if device.platform != SignerDevice.Platform.ANDROID:  # la CIE senza PIN oggi la legge solo l'app Android
        pending = pending.exclude(access_method="nis")
    return pending


def describe(request):
    """Ciò che il Signer mostra prima di chiedere il PIN: titolo, versione, impronta e codice di controllo."""
    if request.purpose == SignatureRequest.Purpose.TEST:
        title, version = "Documento di prova (nessun dato sanitario)", None
    elif request.purpose == SignatureRequest.Purpose.ACCEPTANCE:
        title, version = "Accettazione delle condizioni della firma con CIE", None
    elif request.purpose == SignatureRequest.Purpose.ENROLL:
        title, version = "Registrazione della tua CIE (senza il suo PIN)", None
    elif request.purpose == SignatureRequest.Purpose.ACCESS:
        title = (request.access_document.title if request.access_document_id
                 else f"tutti i documenti dell'ospite {request.access_guest} (esportazione)")
        version = None
    else:
        title, version = request.version.document.title, request.version.number
    return {
        "id": str(request.id), "purpose": request.purpose, "title": title, "version": version,
        "document_sha256": request.version_sha256, "verify_code": request.verify_code, "reason": request.reason,
        "expires_at": request.expires_at.isoformat(), "status": request.status,
        "method": request.access_method or "cie",
    }


def _rotate_nonce(request):
    nonce = secrets.token_urlsafe(24)
    request.nonce_hash = _hash(nonce)
    request.updated_at = timezone.now()
    return nonce


def _locked(request_id, device, nonce=None, states=None):
    """Richiesta bloccata per l'aggiornamento; controlla proprietario, dispositivo, scadenza, nonce e stato."""
    request = SignatureRequest.objects.select_for_update().filter(pk=request_id).first()
    if request is None or request.user_id != device.user_id:
        raise SignatureError("Richiesta di firma non trovata.", "not_found")
    if request.device_id is not None and request.device_id != device.pk:
        raise SignatureError("La richiesta è gestita da un altro dispositivo.", "wrong_device")
    if request.is_active and timezone.now() > request.expires_at + (
            datetime.timedelta(minutes=2) if request.status == Status.VERIFYING else datetime.timedelta()):
        raise SignatureError("Richiesta scaduta: avviare una nuova firma dal FASAS.", "expired")
    if nonce is not None and not hmac.compare_digest(request.nonce_hash, _hash(nonce or "")):
        raise SignatureError("Passo non valido o già eseguito (nonce errato).", "bad_nonce")
    if states is not None and request.status not in states:
        raise SignatureError(f"Operazione non ammessa nello stato «{request.get_status_display()}».", "bad_state")
    return request


def claim(request_id, device):
    """Il Signer prende in carico la richiesta (dopo la conferma dell'utente): da qui la usa solo questo dispositivo."""
    with transaction.atomic():
        request = _locked(request_id, device, states=(Status.WAITING,))
        if request.access_method == "nis":  # sfida per l'autenticazione interna della carta (senza PIN della carta)
            request.prepared = {"challenge": external.b64(secrets.token_bytes(nis_protocol.CHALLENGE_BYTES))}
            request.status = Status.AUTHORIZING
        request.device = device
        nonce = _rotate_nonce(request)
        request.save()
    return request, nonce


def report_state(request_id, device, nonce, state, attempts_left=None):
    """Avanzamento visibile nel FASAS: carta mancante/rilevata, PIN errato (con tentativi rimasti), firma in corso."""
    if state not in DEVICE_STATES:
        raise SignatureError("Stato non riconosciuto.", "bad_state")
    # Sul telefono (NFC) il PIN si verifica all'apertura del canale sicuro, prima di leggere il certificato
    allowed = {"card_missing": (Status.WAITING,), "card": (Status.WAITING,),
               "pin_wrong": (Status.WAITING, Status.CARD, Status.AUTHORIZING), "signing": (Status.AUTHORIZING,)}[state]
    with transaction.atomic():
        request = _locked(request_id, device, nonce, states=allowed)
        if state == "card_missing":
            request.error_code, request.error_message = "card_absent", DEVICE_ERRORS["card_absent"]
        elif state == "card":
            request.status, request.error_code, request.error_message = Status.CARD, "", ""
        elif state == "pin_wrong":
            request.error_code, request.error_message = "pin_wrong", DEVICE_ERRORS["pin_wrong"]
            request.pin_attempts_left = attempts_left if isinstance(attempts_left, int) and attempts_left >= 0 else None
        else:
            request.status, request.error_code, request.error_message = Status.SIGNING, "", ""
        new_nonce = _rotate_nonce(request)
        request.save()
    return request, new_nonce


def report_error(request_id, device, nonce, code, attempts_left=None):
    code = code if code in DEVICE_ERRORS else "device_error"
    with transaction.atomic():
        request = _locked(request_id, device, nonce, states=SignatureRequest.CANCELLABLE)
        if code == "pin_blocked":
            request.pin_attempts_left = 0
        _close(request, Status.CANCELLED if code == "cancelled" else Status.FAILED, code, DEVICE_ERRORS[code])
    return request


def handle_failure(request_id, exc):
    """Dopo un errore in un passo del dispositivo: chiude le richieste scadute (fuori dalla transazione annullata)."""
    if exc.code == "expired":
        request = SignatureRequest.objects.filter(pk=request_id).first()
        if request is not None:
            expire_if_needed(request)


def fail(request_id, code, message):
    """Chiude la richiesta per un errore rilevato dal server (in una transazione propria: l'esito resta registrato)."""
    with transaction.atomic():
        request = SignatureRequest.objects.select_for_update().filter(pk=request_id).first()
        if request is not None and request.is_active:
            _close(request, Status.FAILED, code, message)
    return request


def _source_pdf(request):
    from fasas.documents.services import read_version

    if request.purpose in (SignatureRequest.Purpose.TEST, SignatureRequest.Purpose.ACCEPTANCE):
        data = read_encrypted(request.result_storage)
    else:
        data = read_version(request.version, audit=False)
    if hashlib.sha256(data).hexdigest() != request.version_sha256:
        raise SignatureError("Il documento è cambiato dopo la richiesta di firma.", "version_changed")
    return data


def submit_certificate(request_id, device, nonce, certificate_b64):
    """
    Il Signer invia il certificato letto dalla carta. Si verifica che sia del firmatario e (per i documenti)
    emesso dalla CA della CIE, poi si prepara il PDF: in risposta il dispositivo riceve ciò che deve firmare.
    """
    with transaction.atomic():
        request = _locked(request_id, device, nonce, states=(Status.WAITING, Status.CARD))
        if request.access_method == "nis":
            raise SignatureError("Questa richiesta non usa il PIN della carta.", "bad_state")
        request.status, request.error_code, request.error_message = Status.CARD, "", ""
        request.updated_at = timezone.now()
        request.save()
    try:
        cert = external.load_certificate(external.unb64(certificate_b64, "Certificato"))
        info = external.check_certificate_for_user(cert, request.user)
        chain_note = ""
        if request.purpose in (SignatureRequest.Purpose.DOCUMENT, SignatureRequest.Purpose.ACCEPTANCE,
                               SignatureRequest.Purpose.ACCESS):
            external.validate_certificate_chain(cert)
        else:
            try:
                external.validate_certificate_chain(cert)
            except SignatureError as exc:  # nella prova si segnala ma si prosegue: serve a collaudare il dispositivo
                chain_note = str(exc)
        if request.purpose == SignatureRequest.Purpose.ACCESS:
            prepared, prepared_pdf = _access_challenge(request), None
        else:
            source = _source_pdf(request)
            location = request.location or "FASAS"
            prepared, prepared_pdf = external.prepare(
                source, cert, external.intermediate_certs(), field_name=next_field_name(source),
                reason=request.reason, location=location, with_timestamp=request.with_timestamp,
            )
    except SignatureError as exc:
        fail(request.pk, exc.code, str(exc))
        raise
    with transaction.atomic():
        request = _locked(request_id, device, states=(Status.CARD,))
        old_storage = request.prepared_storage
        request.prepared_storage = store_encrypted(prepared_pdf, "signing/requests") if prepared_pdf else ""
        request.prepared = prepared.to_dict()
        request.certificate = certificate_b64
        request.certificate_subject = info["subject"]
        request.certificate_issuer = info["issuer"]
        request.certificate_serial = info["serial"]
        request.certificate_fingerprint = info["fingerprint"]
        request.verification = {"chain_note": chain_note} if chain_note else {}
        request.status = Status.AUTHORIZING
        new_nonce = _rotate_nonce(request)
        request.save()
    if old_storage:
        delete_stored(old_storage)
    return request, new_nonce, prepared


def submit_signature(request_id, device, nonce, signature_b64):
    """Verifica il valore di firma, completa il PDF, lo verifica e lo archivia come nuova versione firmata."""
    with transaction.atomic():
        request = _locked(request_id, device, nonce, states=(Status.AUTHORIZING, Status.SIGNING))
        request.status, request.error_code, request.error_message = Status.VERIFYING, "", ""
        _rotate_nonce(request)  # il valore di firma si accetta una sola volta
        request.save()
    try:
        signature_value = external.unb64(signature_b64, "Valore di firma")
        cert = external.load_certificate(external.unb64(request.certificate))
        prepared = external.PreparedSignature.from_dict(request.prepared)
        external.check_signature_value(cert, prepared, signature_value)
        if request.purpose == SignatureRequest.Purpose.ACCESS:
            return _grant_access(request.pk)
        source = _source_pdf(request)
        signed = external.finish(read_encrypted(request.prepared_storage), prepared, cert,
                                 external.intermediate_certs(), signature_value, with_timestamp=request.with_timestamp)
        if not signed.startswith(source):
            raise SignatureError("Il PDF firmato non contiene il documento originale invariato.", "verify_failed")
        try:
            verification = external.validate_last_signature(signed, cert, prepared.field_name)
        except SignatureError as exc:
            if request.purpose != SignatureRequest.Purpose.TEST or exc.code != "cert_untrusted":
                raise
            verification = {"trusted": False, "intact": True, "valid": True, "note": str(exc)}
    except SignatureError as exc:
        fail(request.pk, exc.code, str(exc))
        raise
    try:
        return _archive(request.pk, signed, verification)
    except SignatureError:
        raise
    except Exception as exc:  # es. ospite archiviato nel frattempo: la richiesta non resta sospesa
        fail(request.pk, "archive_failed", "Archiviazione del documento firmato non riuscita.")
        raise SignatureError("Archiviazione del documento firmato non riuscita.", "archive_failed") from exc


def _archive_acceptance(request, signed, level):
    from .fea_terms import terms, terms_sha256
    from .models import FEAAcceptance

    version, text = terms()
    now = timezone.now()
    FEAAcceptance.objects.filter(user=request.user, revoked_at__isnull=True).update(
        revoked_at=now, revoked_reason="Sostituita da una nuova accettazione")
    acceptance = FEAAcceptance.objects.create(
        user=request.user, request=request, accepted_at=now, terms_version=version, terms_sha256=terms_sha256(text),
        signed_storage=store_encrypted(signed, "signing/acceptances"), signed_sha256=hashlib.sha256(signed).hexdigest(),
        certificate=request.certificate, certificate_subject=request.certificate_subject,
        certificate_serial=request.certificate_serial, is_test_card=request.is_test_card,
        retain_until=(now + datetime.timedelta(days=round(365.25 * settings.FASAS_FEA_RETENTION_YEARS))).date(),
    )
    log_event(AuditLog.Action.SIGN, acceptance, user=request.user,
              changes={"accettazione_FEA": [None, version], "certificato": [None, request.certificate_subject],
                       "formato": [None, f"PAdES-{level}"]}, reason=request.reason)
    return acceptance


def _archive(request_id, signed, verification):
    from fasas.documents.services import add_version

    with transaction.atomic():
        request = SignatureRequest.objects.select_for_update().get(pk=request_id)
        if request.status != Status.VERIFYING:
            raise SignatureError("Richiesta chiusa durante la verifica.", "bad_state")
        level = "B-T" if verification.get("timestamped") else "B-B"
        request.verification = {**request.verification, **verification, "level": f"PAdES-{level}"}
        if request.purpose == SignatureRequest.Purpose.TEST:
            delete_stored(request.result_storage)
            request.result_storage = store_encrypted(signed, "signing/tests")
        elif request.purpose == SignatureRequest.Purpose.ACCEPTANCE:
            _archive_acceptance(request, signed, level)
        else:
            version = request.version
            # Carta di prova (solo installazioni di prova): firma vera ma senza valore legale, e lo si dichiara
            test_card = request.is_test_card
            signed_version = add_version(
                version.document, signed,
                version.original_name.rsplit(".", 1)[0] + ("_firmato_PROVA.pdf" if test_card else "_firmato_CIE.pdf"),
                request.user, content_type="application/pdf", is_signed=True, signature_request=request,
                note=(f"Firma con CARTA DI PROVA di {request.user} – nessun valore legale" if test_card
                      else f"Firma elettronica avanzata con CIE di {request.user}"),
            )
            request.signature = Signature.objects.create(
                source_version=version, signed_version=signed_version, signer=request.user,
                provider="cie-prova" if test_card else "cie",
                certificate_subject=request.certificate_subject, certificate_issuer=request.certificate_issuer,
                certificate_serial=request.certificate_serial, reason=request.reason,
                signature_format=f"PAdES-{level}", timestamped=level == "B-T",
                legal_level="" if test_card else LegalLevel.FEA,
            )
            log_event(AuditLog.Action.SIGN, signed_version, user=request.user, guest=version.document.guest,
                      changes={"firma": [None, "carta di prova" if test_card else "FEA con CIE"],
                               "certificato": [None, request.certificate_subject],
                               "richiesta": [None, request.verify_code], "sha256": [None, signed_version.sha256]},
                      reason=request.reason)
        _close(request, Status.SIGNED)
    return request
