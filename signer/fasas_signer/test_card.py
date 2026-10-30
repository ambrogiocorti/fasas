"""
Carta di prova software, al posto della CIE quando non c'è un lettore NFC.

NON è una CIE e le sue firme non hanno valore legale: la crea «manage.py fasas_carta_di_prova» su un FASAS di prova,
con una CA marcata «SOLO PROVA». Funziona solo verso un FASAS sullo stesso computer, e il FASAS la rifiuta quando
non è un'installazione di prova. Il PIN protegge il file della chiave: tre errori di fila bloccano la carta finché
il Signer non viene riavviato.
"""
import platform
from pathlib import Path

from .card import CardError


class TestCard:
    is_test = True

    def __init__(self, path):
        self.path = Path(path)
        self.certificate_path = self.path.with_suffix(".cer")
        self.attempts_left = 3

    def status(self):
        present = self.card_present()
        return {"os": f"{platform.system()} {platform.release()}"[:80], "middleware_found": present,
                "middleware": "CARTA DI PROVA (software) – non è una CIE", "middleware_path": str(self.path)[:200],
                "readers": ["Nessun lettore: carta di prova"], "card_present": present,
                "mechanisms": ["SHA256_RSA_PKCS"]}

    def card_present(self):
        return self.path.exists() and self.certificate_path.exists()

    def certificate(self):
        if not self.card_present():
            raise CardError("card_absent", f"Carta di prova non trovata: {self.path}")
        return self.certificate_path.read_bytes()

    def sign(self, pin, to_be_signed, digest_info, on_login=None):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import pkcs12

        if self.attempts_left == 0:
            raise CardError("pin_blocked", "PIN della carta di prova bloccato: riavviare il Signer.", 0)
        try:
            key, _, _ = pkcs12.load_key_and_certificates(self.path.read_bytes(), pin.encode())
        except ValueError:
            self.attempts_left -= 1
            if self.attempts_left == 0:
                raise CardError("pin_blocked", "PIN della carta di prova bloccato: riavviare il Signer.", 0) from None
            raise CardError("pin_wrong", "PIN errato.", self.attempts_left) from None
        except OSError as exc:
            raise CardError("card_removed", "File della carta di prova non leggibile.") from exc
        self.attempts_left = 3
        if on_login is not None:
            on_login()
        return key.sign(to_be_signed, padding.PKCS1v15(), hashes.SHA256())
