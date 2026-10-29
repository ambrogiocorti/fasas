"""
Flusso di firma del FASAS Signer, indipendente dall'interfaccia (finestre o terminale).

Per ogni richiesta: conferma dell'utente (titolo, versione e codice di controllo uguale a quello mostrato dal
FASAS), presa in carico, attesa della carta, lettura del certificato, PIN digitato qui, firma, invio del solo
valore di firma. Il PIN non viene mai inviato al server, scritto su disco o nei log.
"""
import base64
import hashlib
import logging
import threading
import time

from .card import CardError
from .client import ServerError

log = logging.getLogger("fasas_signer")  # solo identificativi delle richieste: mai titoli, PIN o certificati
SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def b64(data):
    return base64.b64encode(data).decode("ascii")


class UserInterface:
    """Interfaccia minima richiesta dal motore (implementata dalla finestra Tk e dalla console)."""

    def confirm(self, request) -> bool:
        raise NotImplementedError

    def ask_pin(self, request, message=None):
        """Restituisce il PIN digitato oppure None se l'utente annulla."""
        raise NotImplementedError

    def info(self, text):
        pass

    def done(self, request, result):
        pass

    def failed(self, request, message):
        pass


class SigningEngine:
    def __init__(self, client, card, ui, card_wait=60):
        self.client, self.card, self.ui, self.card_wait = client, card, ui, card_wait

    def handle(self, request):
        request_id = request["id"]
        if not self.ui.confirm(request):
            claimed = self.client.claim(request_id)
            self.client.error(request_id, claimed["nonce"], "cancelled")
            log.info("Richiesta %s rifiutata dall'utente", request_id)
            return "cancelled"
        nonce = None
        try:
            claimed = self.client.claim(request_id)
            nonce = claimed["nonce"]
            if claimed["verify_code"] != request["verify_code"]:
                raise CardError("device_error", "Il codice di controllo non coincide: firma interrotta.")
            nonce = self._wait_card(request_id, nonce)
            certificate = self.card.certificate()
            prepared = self.client.certificate(request_id, nonce, b64(certificate))
            nonce = prepared["nonce"]
            to_be_signed = base64.b64decode(prepared["to_be_signed"])
            digest_info = base64.b64decode(prepared["digest_info"])
            if digest_info != SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(to_be_signed).digest():
                raise CardError("device_error", "Dati da firmare incoerenti ricevuti dal server: firma interrotta.")
            return self._authorize_and_sign(request, nonce, to_be_signed, digest_info)
        except CardError as exc:
            log.info("Richiesta %s: errore della carta %s", request_id, exc.code)
            self._report(request_id, getattr(exc, "nonce", None) or nonce, exc.code)
            self.ui.failed(request, str(exc))
            return "failed"
        except ServerError as exc:
            log.info("Richiesta %s: il server ha risposto %s", request_id, exc.code)
            self.ui.failed(request, str(exc))
            return "failed"

    def _report(self, request_id, nonce, code):
        if nonce is None:
            return
        try:
            self.client.error(request_id, nonce, code)
        except ServerError:
            pass  # la richiesta può essere già chiusa (scaduta o annullata dal FASAS)

    def _wait_card(self, request_id, nonce):
        deadline = time.monotonic() + self.card_wait
        reported = False
        while not self.card.card_present():
            if not reported:
                nonce = self.client.state(request_id, nonce, "card_missing")["nonce"]
                self.ui.info("Appoggia la CIE sul lettore e tienila ferma.")
                reported = True
            if time.monotonic() > deadline:
                absent = CardError("card_absent", "Nessuna CIE appoggiata sul lettore entro il tempo previsto.")
                absent.nonce = nonce
                raise absent
            time.sleep(1)
        return self.client.state(request_id, nonce, "card")["nonce"]

    def _authorize_and_sign(self, request, nonce, to_be_signed, digest_info):
        request_id = request["id"]
        message = None
        while True:
            pin = self.ui.ask_pin(request, message)
            if pin is None:
                cancelled = CardError("cancelled", "Firma annullata.")
                cancelled.nonce = nonce
                raise cancelled
            state = {"nonce": nonce}

            def on_login(state=state):
                state["nonce"] = self.client.state(request_id, state["nonce"], "signing")["nonce"]
                self.ui.info("Firma in corso: non allontanare la carta.")

            try:
                signature = self.card.sign(pin, to_be_signed, digest_info, on_login=on_login)
            except CardError as exc:
                if exc.code != "pin_wrong":
                    exc.nonce = state["nonce"]  # dopo la verifica del PIN il nonce è già cambiato
                    raise
                nonce = self.client.state(request_id, state["nonce"], "pin_wrong", exc.attempts_left)["nonce"]
                left = f" Tentativi rimasti: {exc.attempts_left}." if exc.attempts_left is not None else ""
                message = f"PIN errato.{left} Dopo 3 errori il PIN si blocca."
                continue
            finally:
                pin = None  # noqa: F841 – il PIN non resta in memoria più del necessario
            result = self.client.sign(request_id, state["nonce"], b64(signature))
            log.info("Richiesta %s firmata", request_id)
            self.ui.done(request, result)
            return result.get("status", "signed")


class Service:
    """Ciclo principale: stato dei componenti, attesa delle richieste, una firma alla volta."""

    def __init__(self, client, card, ui, status_every=60):
        self.client, self.card, self.ui = client, card, ui
        self.engine = SigningEngine(client, card, ui)
        self.status_every = status_every
        self.stop_event = threading.Event()
        self.last_error = ""

    def report_status(self):
        status = self.card.status()
        self.client.report_status(status)
        return status

    def run(self, wait=10, once=False):
        last_status = 0.0
        while not self.stop_event.is_set():
            try:
                if time.monotonic() - last_status > self.status_every:
                    self.report_status()
                    last_status = time.monotonic()
                for request in self.client.pending(wait=0 if once else wait):
                    self.engine.handle(request)
                self.last_error = ""
            except ServerError as exc:
                self.last_error = str(exc)
                if exc.status == 401:
                    self.ui.failed(None, "Dispositivo non abbinato o revocato: abbinarlo di nuovo dal FASAS.")
                    return
                self.stop_event.wait(5)
            if once:
                return
