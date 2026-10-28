"""
Cifratura dei file a riposo.

Documenti e report sono cifrati con Fernet (AES-128-CBC + HMAC-SHA256) usando MultiFernet:
la prima chiave in FASAS_ENCRYPTION_KEYS cifra, tutte possono decifrare (rotazione chiavi).
I backup usano invece un formato a blocchi AES-256-GCM (vedi fasas.backups.crypto) perché
possono superare la memoria disponibile.
"""
import hashlib
import uuid

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


class DecryptionError(Exception):
    pass


def _cipher():
    keys = settings.FASAS_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured("FASAS_ENCRYPTION_KEYS non configurata: impossibile cifrare i file.")
    return MultiFernet([Fernet(key.encode() if isinstance(key, str) else key) for key in keys])


def generate_key():
    return Fernet.generate_key().decode()


def encrypt(data: bytes) -> bytes:
    return _cipher().encrypt(data)


def decrypt(token: bytes) -> bytes:
    try:
        return _cipher().decrypt(token)
    except InvalidToken as exc:
        raise DecryptionError("File non decifrabile: chiave errata o file alterato.") from exc


def rotate(token: bytes) -> bytes:
    """Ricifra con la chiave primaria corrente."""
    return _cipher().rotate(token)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_encrypted(data: bytes, folder: str) -> str:
    """Cifra e salva su storage. Il nome file non contiene informazioni sull'ospite."""
    name = f"{folder}/{uuid.uuid4().hex}.enc"
    return default_storage.save(name, ContentFile(encrypt(data)))


def read_encrypted(name: str) -> bytes:
    with default_storage.open(name, "rb") as handle:
        return decrypt(handle.read())


def delete_stored(name: str):
    if name and default_storage.exists(name):
        default_storage.delete(name)
