"""
Client delle API /api/firma/v1/ del FASAS.

Il Signer contatta il server in uscita (HTTPS con verifica del certificato): non apre porte sul computer,
quindi nessuna pagina web può comandarlo. Il token del dispositivo viaggia solo nell'intestazione Authorization.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ServerError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def _ssl_context():
    context = ssl.create_default_context()
    try:  # nei pacchetti PyInstaller l'archivio dei certificati di sistema può mancare
        import certifi

        context.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return context


class ServerClient:
    def __init__(self, base_url, token="", allow_http=False, timeout=30):
        parsed = urllib.parse.urlsplit(base_url.strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ValueError("Indirizzo del FASAS non valido (es. https://fasas.esempio.it/).")
        if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS and not allow_http:
            raise ValueError("Il FASAS va raggiunto in HTTPS: con HTTP il token e la firma viaggerebbero in chiaro.")
        self.base = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/api/firma/v1/"
        self.token, self.timeout = token, timeout
        self._context = _ssl_context() if parsed.scheme == "https" else None

    def _call(self, method, path, data=None, timeout=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, data=body, method=method, headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": f"FASAS-Signer/{__version__}",
            **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
        })
        try:
            # schema già limitato a https (o http locale) nel costruttore
            with urllib.request.urlopen(request, timeout=timeout or self.timeout,  # nosec B310
                                        context=self._context) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read() or b"{}")
            except ValueError:
                payload = {}
            raise ServerError(exc.code, payload.get("error", "http_error"),
                              payload.get("message", f"Errore del server ({exc.code}).")) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ServerError(0, "network", "FASAS non raggiungibile: controllare la connessione.") from exc

    def pair(self, code, name, platform, app_version=__version__):
        data = self._call("POST", "abbina/", {"code": code, "name": name, "platform": platform,
                                              "app_version": app_version})
        self.token = data["token"]
        return data

    def me(self):
        return self._call("GET", "dispositivo/")

    def report_status(self, status):
        return self._call("POST", "dispositivo/stato/", {**status, "app_version": __version__})

    def pending(self, wait=10):
        return self._call("GET", f"richieste/?attesa={int(wait)}", timeout=wait + self.timeout)["requests"]

    def claim(self, request_id):
        return self._call("POST", f"richieste/{request_id}/prendi/")

    def state(self, request_id, nonce, state, attempts_left=None):
        return self._call("POST", f"richieste/{request_id}/stato/",
                          {"nonce": nonce, "state": state, "attempts_left": attempts_left})

    def certificate(self, request_id, nonce, certificate_b64):
        return self._call("POST", f"richieste/{request_id}/certificato/", {"nonce": nonce, "certificate": certificate_b64})

    def sign(self, request_id, nonce, signature_b64):
        return self._call("POST", f"richieste/{request_id}/firma/", {"nonce": nonce, "signature": signature_b64})

    def error(self, request_id, nonce, code):
        return self._call("POST", f"richieste/{request_id}/errore/", {"nonce": nonce, "code": code})
