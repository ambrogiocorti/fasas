"""
Custodia delle chiavi.

- Impronte: un'impronta breve (SHA-256, 16 caratteri) identifica ogni chiave senza rivelarla; si annota sul foglio
  di custodia e si confronta in seguito.
- Verifica: al primo controllo si salva un testo cifrato con le chiavi in uso (KeyCanary); poi ogni controllo di
  salute prova a decifrarlo. Se fallisce, la chiave configurata non è quella con cui sono cifrati i dati.
- Busta di custodia: file cifrato con una frase segreta (scrypt + AES-256-GCM) che contiene tutte le chiavi, da
  conservare fuori dal server (cassaforte, gestore di password della direzione). Senza le chiavi documenti e
  backup non sono recuperabili.
"""
import base64
import hashlib
import io
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from django.conf import settings
from django.utils import timezone

ENVELOPE_MAGIC = b"FASASKEY1"
CANARY_TEXT = b"FASAS: verifica della chiave"
SECRET_SETTINGS = [
    ("DJANGO_SECRET_KEY", "SECRET_KEY"), ("FASAS_ENCRYPTION_KEYS", "FASAS_ENCRYPTION_KEYS"),
    ("FASAS_BACKUP_KEY", "FASAS_BACKUP_KEY"), ("FASAS_VAPID_PRIVATE_KEY", "FASAS_VAPID_PRIVATE_KEY"),
    ("FASAS_OFFSITE_SECRET_KEY", "FASAS_OFFSITE_SECRET_KEY"), ("FASAS_HEALTH_TOKEN", "FASAS_HEALTH_TOKEN"),
]


class EnvelopeError(Exception):
    pass


def fingerprint(key):
    return hashlib.sha256(str(key).encode()).hexdigest()[:16]


def fingerprints():
    keys = settings.FASAS_ENCRYPTION_KEYS
    return {
        "documenti (chiave in uso)": fingerprint(keys[0]) if keys else "—",
        "documenti (chiavi precedenti)": ", ".join(fingerprint(k) for k in keys[1:]) or "—",
        "backup": fingerprint(settings.FASAS_BACKUP_KEY) if settings.FASAS_BACKUP_KEY else "—",
    }


def _encrypt_backup(data):
    from fasas.backups.crypto import encrypt_stream

    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out)
    return out.getvalue()


def _decrypt_backup(token):
    from fasas.backups.crypto import decrypt_stream

    out = io.BytesIO()
    decrypt_stream(io.BytesIO(bytes(token)), out)
    return out.getvalue()


def check_keys():
    """[(tipo, esito, descrizione)]: esito «ok» o «error». Crea le verifiche alla prima esecuzione."""
    from fasas.core import encryption

    from .models import KeyCanary

    results = []
    for kind, encrypt, decrypt, key in (
        ("documenti", encryption.encrypt, encryption.decrypt, (settings.FASAS_ENCRYPTION_KEYS or [""])[0]),
        ("backup", _encrypt_backup, _decrypt_backup, settings.FASAS_BACKUP_KEY),
    ):
        if not key:
            results.append((kind, "error", "chiave non configurata"))
            continue
        canary = KeyCanary.objects.filter(kind=kind).first()
        if canary is None:
            KeyCanary.objects.create(kind=kind, token=encrypt(CANARY_TEXT), fingerprint=fingerprint(key))
            results.append((kind, "ok", f"chiave registrata (impronta {fingerprint(key)})"))
            continue
        try:
            ok = decrypt(bytes(canary.token)) == CANARY_TEXT
        except Exception:
            ok = False
        results.append((kind, "ok" if ok else "error", "chiave corretta" if ok else
                        f"la chiave configurata non apre i dati: serve quella con impronta {canary.fingerprint}"))
    return results


def _derive(passphrase, salt):
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(passphrase.encode())


def make_envelope(passphrase, community=""):
    """Busta di custodia cifrata con la frase segreta: contiene i segreti configurati, per esteso."""
    if len(passphrase) < 12:
        raise EnvelopeError("La frase segreta deve avere almeno 12 caratteri.")
    secrets_map = {}
    for env_name, setting in SECRET_SETTINGS:
        value = getattr(settings, setting, "")
        if isinstance(value, list):
            value = ",".join(value)
        if value:
            secrets_map[env_name] = value
    payload = json.dumps({"created_at": timezone.now().isoformat(), "community": community,
                          "fingerprints": fingerprints(), "secrets": secrets_map}).encode()
    salt, nonce = os.urandom(16), os.urandom(12)
    return ENVELOPE_MAGIC + salt + nonce + AESGCM(_derive(passphrase, salt)).encrypt(nonce, payload, ENVELOPE_MAGIC)


def open_envelope(data, passphrase):
    if not data.startswith(ENVELOPE_MAGIC):
        raise EnvelopeError("Non è una busta di custodia del FASAS.")
    salt, nonce = data[9:25], data[25:37]
    try:
        payload = AESGCM(_derive(passphrase, salt)).decrypt(nonce, data[37:], ENVELOPE_MAGIC)
    except InvalidTag as exc:
        raise EnvelopeError("Frase segreta errata o busta danneggiata.") from exc
    return json.loads(payload)


def env_lines(envelope):
    return [f"{name}={value}" for name, value in envelope["secrets"].items()]


def b64(data):
    return base64.b64encode(data).decode()
