"""
Client per la firma remota qualificata tramite API CSC (Cloud Signature Consortium, v1.0.4).

Le API CSC sono lo standard europeo per la firma remota: le espongono i principali prestatori
qualificati (QTSP). Il documento non lascia mai il server FASAS: al prestatore viene inviata
solo l'impronta (hash) da firmare; la chiave privata resta nel suo HSM e si sblocca con PIN e/o OTP
del medico, che FASAS non salva.

Flusso:
  1. accesso al servizio: «basic» (utente e password del medico presso il prestatore, chiamata
     auth/login), «oauth2» (credenziali client della struttura) o «token» statico;
  2. credentials/list e credentials/info: certificato, catena, algoritmi, PIN e OTP richiesti;
  3. eventualmente credentials/sendOTP (OTP via SMS);
  4. credentials/authorize con PIN/OTP e le impronte da firmare → SAD (Signature Activation Data);
  5. signatures/signHash → firma, inserita da pyHanko nel PDF (PAdES).
"""
import asyncio
import base64
import datetime
from dataclasses import dataclass
from io import BytesIO

import aiohttp
from asn1crypto import algos, x509
from django.conf import settings
from pyhanko.sign.signers.csc_signer import CSCAuthorizationManager, CSCCredentialInfo, CSCServiceSessionInfo

from .providers import SignatureError

ERROR_MESSAGES = {
    "invalid_pin": "PIN non corretto.",
    "invalid_otp": "OTP non corretto o scaduto.",
    "invalid_grant": "Credenziali di accesso al servizio di firma non corrette.",
    "invalid_client": "Credenziali della struttura presso il servizio di firma non valide.",
    "access_denied": "Accesso negato dal servizio di firma.",
    "expired_token": "Sessione con il servizio di firma scaduta: ripetere l'operazione.",
    "invalid_token": "Sessione con il servizio di firma scaduta: ripetere l'operazione.",
}


@dataclass
class CSCConfig:
    service_url: str
    api_version: str = "v1"
    auth: str = "basic"
    token_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scope: str = "service"
    static_token: str = ""
    timeout: int = 30

    @classmethod
    def from_settings(cls):
        url = (settings.FASAS_CSC_SERVICE_URL or "").rstrip("/")
        if not url:
            raise SignatureError("Firma remota non configurata: manca FASAS_CSC_SERVICE_URL (vedi docs/FIRMA_DIGITALE.md).")
        return cls(service_url=url, api_version=settings.FASAS_CSC_API_VERSION, auth=settings.FASAS_CSC_AUTH,
                   token_url=settings.FASAS_CSC_OAUTH_TOKEN_URL, client_id=settings.FASAS_CSC_CLIENT_ID,
                   client_secret=settings.FASAS_CSC_CLIENT_SECRET, scope=settings.FASAS_CSC_OAUTH_SCOPE,
                   static_token=settings.FASAS_CSC_TOKEN, timeout=settings.FASAS_CSC_TIMEOUT)

    @property
    def needs_user_password(self):
        return self.auth == "basic"

    def endpoint(self, name):
        return f"{self.service_url}/csc/{self.api_version}/{name}"


@dataclass
class RemoteCredential:
    credential_id: str
    subject: str
    issuer: str
    serial: str
    valid_from: datetime.datetime | None
    valid_to: datetime.datetime | None
    pin_required: bool
    otp_type: str  # "", "offline" (app/token), "online" (SMS)
    auth_mode: str
    usable: bool
    problem: str = ""


def _error_message(status, data):
    if isinstance(data, dict):
        code = str(data.get("error", ""))
        if code in ERROR_MESSAGES:
            return ERROR_MESSAGES[code]
        if data.get("error_description"):
            return f"Il servizio di firma ha risposto: {data['error_description']}"
    return f"Il servizio di firma non risponde correttamente (HTTP {status})."


def _parse_csc_time(value):
    if not value:
        return None
    for fmt in ("%Y%m%d%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.datetime.strptime(value, fmt).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def _presence(block):
    return str((block or {}).get("presence", "false")).lower() == "true"


class CSCClient:
    def __init__(self, config: CSCConfig, http: aiohttp.ClientSession):
        self.config = config
        self.http = http

    async def _request(self, method, url, **kwargs):
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        try:
            async with self.http.request(method, url, timeout=timeout, **kwargs) as response:
                try:
                    data = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    data = None
                if response.status >= 400:
                    raise SignatureError(_error_message(response.status, data))
                return data if data is not None else {}
        except aiohttp.ClientError as exc:
            raise SignatureError(f"Servizio di firma non raggiungibile ({exc.__class__.__name__}).") from exc
        except asyncio.TimeoutError as exc:
            raise SignatureError("Il servizio di firma non ha risposto in tempo.") from exc

    async def post(self, endpoint, token, payload):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return await self._request("POST", self.config.endpoint(endpoint), json=payload, headers=headers)

    async def info(self):
        return await self._request("POST", self.config.endpoint("info"), json={})

    async def access_token(self, username="", password=""):
        """Token di accesso al servizio secondo FASAS_CSC_AUTH."""
        if self.config.auth == "token":
            return self.config.static_token
        if self.config.auth == "oauth2":
            data = await self._request("POST", self.config.token_url, data={
                "grant_type": "client_credentials", "client_id": self.config.client_id,
                "client_secret": self.config.client_secret, "scope": self.config.scope,
            })
        else:
            if not username or not password:
                raise SignatureError("Indicare utente e password del servizio di firma.")
            data = await self._request("POST", self.config.endpoint("auth/login"), json={"rememberMe": False},
                                       auth=aiohttp.BasicAuth(username, password))
        token = data.get("access_token")
        if not token:
            raise SignatureError("Il servizio di firma non ha restituito un token di accesso.")
        return token

    async def list_credentials(self, token, user_id=""):
        payload = {"userID": user_id} if user_id and self.config.auth != "basic" else {}
        data = await self.post("credentials/list", token, payload)
        return [str(c) for c in data.get("credentialIDs", [])]

    async def credential_info(self, token, credential_id):
        data = await self.post("credentials/info", token, {
            "credentialID": credential_id, "certificates": "chain", "certInfo": True, "authInfo": True,
        })
        cert = data.get("cert", {})
        key = data.get("key", {})
        otp = data.get("OTP") or {}
        auth_mode = str(data.get("authMode", "explicit"))
        problem = ""
        if str(key.get("status", "enabled")).lower() != "enabled":
            problem = "chiave di firma disabilitata presso il prestatore"
        elif str(cert.get("status", "valid")).lower() != "valid":
            problem = f"certificato {cert.get('status')}"
        elif auth_mode == "oauth2code":
            problem = "il prestatore richiede l'autorizzazione della firma via browser (oauth2code), non supportata"
        return RemoteCredential(
            credential_id=credential_id, subject=str(cert.get("subjectDN", ""))[:255],
            issuer=str(cert.get("issuerDN", ""))[:255], serial=str(cert.get("serialNumber", ""))[:100],
            valid_from=_parse_csc_time(cert.get("validFrom")), valid_to=_parse_csc_time(cert.get("validTo")),
            pin_required=_presence(data.get("PIN")),
            otp_type=str(otp.get("type", "offline")).lower() if _presence(otp) else "",
            auth_mode=auth_mode, usable=not problem, problem=problem,
        ), data

    async def send_otp(self, token, credential_id):
        await self.post("credentials/sendOTP", token, {"credentialID": credential_id})


class FasasAuthorizationManager(CSCAuthorizationManager):
    """Chiede la SAD a credentials/authorize con PIN/OTP digitati dal medico al momento della firma."""

    def __init__(self, session_info, credential_info, client, pin, otp, description):
        super().__init__(session_info, credential_info)
        self.client, self.pin, self.otp, self.description = client, pin, otp, description

    async def authorize_signature(self, hash_b64s):
        pinned = hash_b64s if self.credential_info.hash_pinning_required else None
        payload = self.format_csc_auth_request(num_signatures=len(hash_b64s), pin=self.pin or None,
                                               otp=self.otp or None, hash_b64s=pinned,
                                               description=self.description)
        data = await self.client.post("credentials/authorize", self.csc_session_info.oauth_token, payload)
        return self.parse_csc_auth_response(data)


def session(config=None):
    """Sessione HTTP: rispetta proxy di sistema (HTTPS_PROXY / NO_PROXY)."""
    return aiohttp.ClientSession(trust_env=True)


def run(coro):
    return asyncio.run(coro)


async def discover(config, username, password, wanted_credential=""):
    """Configurazione guidata: accede, elenca le credenziali e legge certificato e modalità di sblocco."""
    async with session() as http:
        client = CSCClient(config, http)
        token = await client.access_token(username, password)
        ids = await client.list_credentials(token, username)
        if wanted_credential:
            ids = [i for i in ids if i == wanted_credential] or [wanted_credential]
        if not ids:
            raise SignatureError("Nessuna credenziale di firma associata a questo utente presso il prestatore.")
        found = []
        for credential_id in ids:
            info, _ = await client.credential_info(token, credential_id)
            found.append(info)
        usable = [c for c in found if c.usable]
        if not usable:
            raise SignatureError("Nessuna credenziale utilizzabile: " + "; ".join(c.problem for c in found))
        return usable, token


async def request_otp(config, credential, username, password, token=None):
    async with session() as http:
        client = CSCClient(config, http)
        token = token or await client.access_token(username, password)
        await client.send_otp(token, credential.remote_credential_id)
        return token


async def sign_pdf_remote(config, credential, pdf_bytes, *, username="", password="", pin="", otp="", token=None,
                          reason="", location="", build_metadata, timestamper=None):
    """Firma il PDF con la credenziale remota. build_metadata(signer) restituisce i PdfSignatureMetadata."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.signers.csc_signer import CSCSigner

    async with session() as http:
        client = CSCClient(config, http)
        token = token or await client.access_token(username, password)
        info_session = CSCServiceSessionInfo(config.service_url, credential.remote_credential_id, oauth_token=token,
                                             api_ver=config.api_version)
        remote, raw = await client.credential_info(token, credential.remote_credential_id)
        if not remote.usable:
            raise SignatureError(f"Credenziale non utilizzabile: {remote.problem}.")
        credential_info = credential_certificates(raw)
        manager = FasasAuthorizationManager(info_session, credential_info, client, pin, otp,
                                            description=reason[:500] or None)
        signer = CSCSigner(http, manager, sign_timeout=config.timeout)
        writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes), strict=False)
        meta = build_metadata(credential_info)
        try:
            out = await signers.PdfSigner(meta, signer=signer, timestamper=timestamper).async_sign_pdf(writer)
        except SignatureError:
            raise
        except Exception as exc:
            cause = exc.__cause__ or exc
            if isinstance(cause, SignatureError):
                raise cause from exc
            raise SignatureError(f"Firma remota non riuscita: {cause}") from exc
        return out.getvalue(), remote


def credential_certificates(raw):
    """Certificato, catena e algoritmi dalla risposta di credentials/info."""
    try:
        certs = [x509.Certificate.load(base64.b64decode(c)) for c in raw["cert"]["certificates"]]
        mechanisms = frozenset(algos.SignedDigestAlgorithmId(oid).native for oid in raw["key"]["algo"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SignatureError("Il servizio di firma non ha restituito certificato e algoritmi validi.") from exc
    if not certs:
        raise SignatureError("Il servizio di firma non ha restituito il certificato del firmatario.")
    return CSCCredentialInfo(
        signing_cert=certs[0], chain=certs[1:], supported_mechanisms=mechanisms,
        max_batch_size=int(raw.get("multisign", 1) or 1), hash_pinning_required=str(raw.get("SCAL", "1")) == "2",
        response_data=raw,
    )
