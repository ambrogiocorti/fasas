"""
Accesso alla CIE tramite il modulo PKCS#11 del Software CIE (Ministero dell'Interno).

- La chiave privata resta nel chip: si chiede alla carta di firmare, non si legge mai la chiave.
- Il PIN (le ultime 4 cifre, dopo l'abbinamento della carta nell'app «CIE ID») va solo al modulo PKCS#11.
- Il certificato pubblico si legge senza PIN; il Software CIE lo espone solo per le carte abbinate.

Meccanismi: CKM_SHA256_RSA_PKCS sugli attributi firmati, oppure CKM_RSA_PKCS sul DigestInfo SHA-256
se il modulo non offre il primo. Il risultato è identico (RSA PKCS#1 v1.5 con SHA-256).
"""
import os
import platform
import sys

# Percorsi indicati dai manuali ufficiali del Software CIE (sovrascrivibili in configurazione)
LIBRARY_CANDIDATES = {
    "windows": [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "CIEPKI.dll"), "CIEPKI.dll"],
    "linux": ["/usr/local/lib/libcie-pkcs11.so", "/usr/lib/libcie-pkcs11.so", "/usr/lib/x86_64-linux-gnu/libcie-pkcs11.so"],
    # Manuale macOS 1.4.2 (pacchetto .pkg); con la versione «Software CIE» dell'App Store va verificato
    "macos": ["/Library/ipzs/libcie-pkcs11.dylib", "/usr/local/lib/libcie-pkcs11.dylib"],
}


class CardError(Exception):
    """Errore della carta con il codice da riferire al FASAS (vedi fasas.signatures.cie.DEVICE_ERRORS)."""

    def __init__(self, code, message, attempts_left=None):
        super().__init__(message)
        self.code = code
        self.attempts_left = attempts_left


def current_os():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux" if sys.platform.startswith("linux") else "other"


def find_library(configured=""):
    if configured:
        return configured if os.path.exists(configured) or os.sep not in configured else ""
    for candidate in LIBRARY_CANDIDATES.get(current_os(), []):
        if os.path.exists(candidate):
            return candidate
    return ""


class Pkcs11Card:
    def __init__(self, library_path=""):
        self.library_path = find_library(library_path)
        self._lib = None

    def _load(self):
        if self._lib is not None:
            return self._lib
        if not self.library_path:
            raise CardError("middleware_missing", "Software CIE non trovato: installarlo o indicare il percorso del modulo PKCS#11.")
        try:
            import pkcs11
        except ImportError as exc:
            raise CardError("device_error", "Componente python-pkcs11 mancante nel FASAS Signer.") from exc
        try:
            self._lib = pkcs11.lib(self.library_path)
        except Exception as exc:  # libreria assente, architettura diversa, dipendenze mancanti
            raise CardError("middleware_missing", f"Impossibile caricare il modulo PKCS#11 ({type(exc).__name__}).") from exc
        return self._lib

    def readers(self):
        """[(descrizione lettore, carta presente)] — non richiede PIN."""
        import pkcs11

        slots = self._load().get_slots(token_present=False)
        return [(slot.slot_description.strip(), bool(slot.flags & pkcs11.SlotFlag.TOKEN_PRESENT)) for slot in slots]

    def status(self):
        """Stato dei componenti da riferire al FASAS (nessun dato personale)."""
        info = {"os": f"{platform.system()} {platform.release()}"[:80], "middleware_path": self.library_path,
                "middleware_found": bool(self.library_path)}
        try:
            lib = self._load()
            info["middleware"] = f"{lib.library_description.strip()} {lib.library_version}"[:80]
            readers = self.readers()
            info["readers"] = [name for name, _ in readers]
            info["card_present"] = any(present for _, present in readers)
            if info["card_present"]:
                info["mechanisms"] = sorted(m.name for m in self._token_slot().get_mechanisms()
                                            if m.name in ("SHA256_RSA_PKCS", "RSA_PKCS"))
        except CardError:
            info["middleware_found"] = False
        except Exception:  # lettore scollegato mentre si interroga
            info["card_present"] = False
        return info

    def _token_slot(self):
        slots = self._load().get_slots(token_present=True)
        if not slots:
            if not self._load().get_slots(token_present=False):
                raise CardError("reader_missing", "Nessun lettore di smart card/NFC collegato.")
            raise CardError("card_absent", "Appoggiare la CIE sul lettore.")
        return slots[0]

    def card_present(self):
        try:
            self._token_slot()
            return True
        except CardError as exc:
            if exc.code in ("card_absent",):
                return False
            raise

    def certificate(self):
        """Certificato (DER) della carta, letto senza PIN."""
        from pkcs11 import Attribute, CertificateType, ObjectClass

        try:
            token = self._token_slot().get_token()
            with token.open() as session:
                certs = list(session.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE,
                                                  Attribute.CERTIFICATE_TYPE: CertificateType.X_509}))
                if not certs:
                    raise CardError("cert_missing", "Sulla carta non c'è un certificato.")
                value = bytes(certs[0][Attribute.VALUE] or b"")
                key_id = bytes(certs[0][Attribute.ID] or b"")
        except CardError:
            raise
        except Exception as exc:
            raise _map(exc) from exc
        if not value:
            raise CardError("card_not_enrolled", "CIE non abbinata a questo computer: abbinarla dall'app «CIE ID».")
        self._key_id = key_id
        return value

    def sign(self, pin, to_be_signed, digest_info, on_login=None):
        """
        Firma con la chiave della carta. Il PIN si usa solo qui e non viene conservato.
        on_login() viene chiamata dopo la verifica del PIN e prima della firma (stato «Firma in corso»).
        """
        from pkcs11 import Attribute, KeyType, Mechanism, ObjectClass

        try:
            slot = self._token_slot()
            mechanisms = slot.get_mechanisms()
            token = slot.get_token()
            with token.open(user_pin=pin) as session:
                query = {Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.KEY_TYPE: KeyType.RSA}
                if getattr(self, "_key_id", b""):
                    query[Attribute.ID] = self._key_id
                keys = list(session.get_objects(query))
                if not keys:
                    raise CardError("cert_missing", "Chiave di firma non trovata sulla carta.")
                key = keys[0]
                if on_login is not None:
                    on_login()
                if Mechanism.SHA256_RSA_PKCS in mechanisms:
                    return bytes(key.sign(to_be_signed, mechanism=Mechanism.SHA256_RSA_PKCS))
                if Mechanism.RSA_PKCS in mechanisms:
                    return bytes(key.sign(digest_info, mechanism=Mechanism.RSA_PKCS))
                raise CardError("unsupported_mechanism", "La carta non offre la firma RSA PKCS#1.")
        except CardError:
            raise
        except Exception as exc:
            raise _map(exc, token if "token" in locals() else None) from exc


def _map(exc, token=None):
    from pkcs11 import exceptions as e

    if isinstance(exc, e.PinLocked):
        return CardError("pin_blocked", "PIN bloccato: sbloccarlo con il PUK dall'app «CIE ID».", 0)
    if isinstance(exc, (e.PinIncorrect, e.PinInvalid, e.PinLenRange)):
        return CardError("pin_wrong", "PIN errato.", _attempts_left(token))
    if isinstance(exc, (e.TokenNotPresent, e.DeviceRemoved, e.SessionClosed, e.SessionHandleInvalid,
                        e.TokenNotRecognised)):
        return CardError("card_removed", "La carta è stata allontanata dal lettore.")
    if isinstance(exc, e.FunctionCancelled):
        return CardError("cancelled", "Operazione annullata.")
    if isinstance(exc, e.MechanismInvalid):
        return CardError("unsupported_mechanism", "Meccanismo di firma non supportato dalla carta.")
    return CardError("device_error", f"Errore del modulo PKCS#11 ({type(exc).__name__}).")


def _attempts_left(token):
    """Dalle segnalazioni del token, se disponibili (non tutti i moduli le aggiornano)."""
    if token is None:
        return None
    try:
        from pkcs11 import TokenFlag

        flags = token.slot.get_token().flags
        if flags & TokenFlag.USER_PIN_LOCKED:
            return 0
        if flags & TokenFlag.USER_PIN_FINAL_TRY:
            return 1
    except Exception:
        return None
    return None
