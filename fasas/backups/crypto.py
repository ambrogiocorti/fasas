"""
Cifratura a blocchi per i backup (AES-256-GCM, streaming).

Formato:  MAGIC(8) | file_id(8) | [len(4) | ciphertext+tag]...
- nonce del blocco = file_id || contatore (4 byte): un riordino dei blocchi fa fallire la decifratura;
- dato associato = 1 per l'ultimo blocco, 0 per gli altri: un file troncato viene rilevato.
"""
import base64
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MAGIC = b"FASASBK1"
CHUNK = 4 * 1024 * 1024


class BackupCryptoError(Exception):
    pass


def generate_key():
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def _key(key=None):
    raw = key or settings.FASAS_BACKUP_KEY
    if not raw:
        raise ImproperlyConfigured("FASAS_BACKUP_KEY non configurata.")
    data = base64.urlsafe_b64decode(raw)
    if len(data) != 32:
        raise ImproperlyConfigured("FASAS_BACKUP_KEY deve essere di 32 byte codificati in base64.")
    return AESGCM(data)


def encrypt_stream(src, dst, key=None):
    aes = _key(key)
    file_id = os.urandom(8)
    dst.write(MAGIC + file_id)
    counter = 0
    current = src.read(CHUNK)
    while True:
        following = src.read(CHUNK)
        last = not following
        nonce = file_id + struct.pack(">I", counter)
        sealed = aes.encrypt(nonce, current, b"\x01" if last else b"\x00")
        dst.write(struct.pack(">I", len(sealed)) + sealed)
        if last:
            break
        current = following
        counter += 1


def decrypt_stream(src, dst, key=None):
    aes = _key(key)
    header = src.read(16)
    if len(header) != 16 or header[:8] != MAGIC:
        raise BackupCryptoError("File di backup non riconosciuto.")
    file_id = header[8:]
    counter = 0

    def read_chunk():
        size_raw = src.read(4)
        if not size_raw:
            return None
        if len(size_raw) != 4:
            raise BackupCryptoError("Backup troncato.")
        (size,) = struct.unpack(">I", size_raw)
        data = src.read(size)
        if len(data) != size:
            raise BackupCryptoError("Backup troncato.")
        return data

    current = read_chunk()
    if current is None:
        raise BackupCryptoError("Backup vuoto.")
    while current is not None:
        following = read_chunk()
        nonce = file_id + struct.pack(">I", counter)
        try:
            dst.write(aes.decrypt(nonce, current, b"\x01" if following is None else b"\x00"))
        except InvalidTag as exc:
            raise BackupCryptoError("Backup alterato, troncato o chiave errata.") from exc
        current = following
        counter += 1
