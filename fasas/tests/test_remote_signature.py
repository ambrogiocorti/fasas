"""Firma remota qualificata: prova completa contro un servizio CSC simulato che firma davvero."""
import asyncio
import base64
import datetime
import io
import threading
from unittest import mock

from aiohttp import web
from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from fasas.documents.models import Document
from fasas.documents.services import create_document, read_version
from fasas.signatures.models import SigningCredential
from fasas.signatures.providers import SignatureError, verify_pdf
from fasas.signatures.services import register_remote, request_otp, sign_version

from .base import FasasTestCase
from .test_documents import sample_pdf

NOW = datetime.datetime.now(datetime.timezone.utc)


def _cert(subject, issuer_name, key, issuer_key, ca=False, eku=None):
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(NOW - datetime.timedelta(days=1)).not_valid_after(NOW + datetime.timedelta(days=700))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if eku:
        builder = builder.add_extension(x509.ExtendedKeyUsage(eku), critical=True)
    elif not ca:
        builder = builder.add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=True, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False),
            critical=True)
    return builder.sign(issuer_key, hashes.SHA256())


CA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CA_CERT = _cert("QTSP Prova CA", "QTSP Prova CA", CA_KEY, CA_KEY, ca=True)
SIGNER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SIGNER_CERT = _cert("Dott.ssa Marta Medico", "QTSP Prova CA", SIGNER_KEY, CA_KEY)


def der_b64(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


class FakeCSCService:
    """Servizio CSC v1 minimo: login, credenziali, OTP via SMS, autorizzazione con hash vincolati, firma."""

    USER, PASSWORD, PIN, OTP = "medico1", "pw-servizio", "1234", "654321"

    def __init__(self):
        self.otp_sent = 0
        self.authorized = {}

    def _check_token(self, request):
        if request.headers.get("Authorization") != "Bearer tok-1":
            raise web.HTTPUnauthorized(text='{"error": "invalid_token"}', content_type="application/json")

    async def info(self, request):
        return web.json_response({"specs": "1.0.4.0", "name": "QTSP di prova", "authType": ["basic"]})

    async def login(self, request):
        auth = request.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(f"{self.USER}:{self.PASSWORD}".encode()).decode()
        if auth != expected:
            return web.json_response({"error": "invalid_grant", "error_description": "bad credentials"}, status=401)
        return web.json_response({"access_token": "tok-1", "expires_in": 3600})

    async def credentials_list(self, request):
        self._check_token(request)
        return web.json_response({"credentialIDs": ["cred-1"]})

    async def credentials_info(self, request):
        self._check_token(request)
        return web.json_response({
            "key": {"status": "enabled", "algo": ["1.2.840.113549.1.1.11"], "len": 2048},
            "cert": {"status": "valid", "certificates": [der_b64(SIGNER_CERT), der_b64(CA_CERT)],
                     "subjectDN": "CN=Dott.ssa Marta Medico", "issuerDN": "CN=QTSP Prova CA",
                     "serialNumber": format(SIGNER_CERT.serial_number, "X"),
                     "validFrom": (NOW - datetime.timedelta(days=1)).strftime("%Y%m%d%H%M%SZ"),
                     "validTo": (NOW + datetime.timedelta(days=700)).strftime("%Y%m%d%H%M%SZ")},
            "authMode": "explicit", "PIN": {"presence": "true"}, "OTP": {"presence": "true", "type": "online"},
            "multisign": 1, "SCAL": "2",
        })

    async def send_otp(self, request):
        self._check_token(request)
        self.otp_sent += 1
        return web.json_response({})

    async def authorize(self, request):
        self._check_token(request)
        body = await request.json()
        if body.get("PIN") != self.PIN:
            return web.json_response({"error": "invalid_pin"}, status=400)
        if not self.otp_sent or body.get("OTP") != self.OTP:
            return web.json_response({"error": "invalid_otp"}, status=400)
        if not body.get("hash"):
            return web.json_response({"error": "invalid_request", "error_description": "hash required"}, status=400)
        self.authorized["sad-1"] = list(body["hash"])
        return web.json_response({"SAD": "sad-1", "expiresIn": 300})

    async def sign_hash(self, request):
        self._check_token(request)
        body = await request.json()
        if self.authorized.get(body.get("SAD")) != body.get("hash"):
            return web.json_response({"error": "invalid_request", "error_description": "SAD/hash"}, status=400)
        signatures = [base64.b64encode(SIGNER_KEY.sign(base64.b64decode(h), padding.PKCS1v15(),
                                                        utils.Prehashed(hashes.SHA256()))).decode()
                      for h in body["hash"]]
        return web.json_response({"signatures": signatures})

    def __enter__(self):
        app = web.Application()
        for path, handler in [("info", self.info), ("auth/login", self.login), ("credentials/list", self.credentials_list),
                              ("credentials/info", self.credentials_info), ("credentials/sendOTP", self.send_otp),
                              ("credentials/authorize", self.authorize), ("signatures/signHash", self.sign_hash)]:
            app.router.add_post(f"/csc/v1/{path}", handler)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

        async def start():
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            site = web.TCPSite(self.runner, "127.0.0.1", 0)
            await site.start()
            return site._server.sockets[0].getsockname()[1]

        self.port = asyncio.run_coroutine_threadsafe(start(), self.loop).result(10)
        self.url = f"http://127.0.0.1:{self.port}"
        return self

    def __exit__(self, *exc):
        asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


def dummy_timestamper():
    from pyhanko.sign.timestamps import DummyTimeStamper

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = _cert("TSA Prova", "QTSP Prova CA", key, CA_KEY, eku=[ExtendedKeyUsageOID.TIME_STAMPING])
    return DummyTimeStamper(
        tsa_cert=asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
        tsa_key=asn1_keys.PrivateKeyInfo.load(key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
    )


class RemoteSignatureTests(FasasTestCase):
    def setUp(self):
        self.service = FakeCSCService().__enter__()
        self.settings_override = override_settings(FASAS_CSC_SERVICE_URL=self.service.url, FASAS_CSC_AUTH="basic",
                                                   FASAS_SIGNATURE_TSA_URL="", FASAS_SIGNATURE_LEVEL="")
        self.settings_override.enable()
        self.document = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione",
                                        user=self.coordinator, data=sample_pdf(), filename="relazione.pdf")

    def tearDown(self):
        self.settings_override.disable()
        self.service.__exit__()

    def connect(self):
        return register_remote(self.doctor, FakeCSCService.USER, FakeCSCService.PASSWORD)

    def test_configuration_reads_certificate_and_unlock_mode(self):
        credential = self.connect()
        self.assertEqual(credential.kind, SigningCredential.Kind.REMOTE)
        self.assertEqual(credential.remote_credential_id, "cred-1")
        self.assertTrue(credential.remote_pin_required)
        self.assertEqual(credential.remote_otp_type, "online")
        self.assertIn("Marta", credential.certificate_subject)
        self.assertTrue(credential.is_valid_now)
        with self.assertRaisesMessage(SignatureError, "non corrette"):
            register_remote(self.doctor, FakeCSCService.USER, "sbagliata")

    def test_sign_with_pin_and_sms_otp_produces_valid_pades(self):
        self.connect()
        token = request_otp(self.doctor, FakeCSCService.PASSWORD)
        self.assertEqual(self.service.otp_sent, 1)
        secrets = {"pin": FakeCSCService.PIN, "otp": FakeCSCService.OTP, "token": token}
        signature = sign_version(self.document.current_version, self.doctor, secrets, "Relazione clinica")
        self.assertEqual(signature.provider, "remote")
        self.assertEqual(signature.signature_format, "PAdES-B-B")
        results = verify_pdf(read_version(signature.signed_version, audit=False))
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["intact"])
        self.assertTrue(results[0]["valid"])
        self.assertIn("Marta", results[0]["signer"])

    def test_wrong_pin_or_otp_is_reported_clearly(self):
        self.connect()
        token = request_otp(self.doctor, FakeCSCService.PASSWORD)
        with self.assertRaisesMessage(SignatureError, "OTP non corretto"):
            sign_version(self.document.current_version, self.doctor,
                         {"pin": FakeCSCService.PIN, "otp": "000000", "token": token})
        with self.assertRaisesMessage(SignatureError, "PIN non corretto"):
            sign_version(self.document.current_version, self.doctor,
                         {"pin": "9999", "otp": FakeCSCService.OTP, "token": token})
        self.assertEqual(self.document.versions.count(), 1)

    def test_timestamp_gives_pades_b_t(self):
        self.connect()
        token = request_otp(self.doctor, FakeCSCService.PASSWORD)
        with override_settings(FASAS_SIGNATURE_TSA_URL="http://tsa.prova"), \
                mock.patch("fasas.signatures.providers.timestamper", dummy_timestamper):
            signature = sign_version(self.document.current_version, self.doctor,
                                     {"pin": FakeCSCService.PIN, "otp": FakeCSCService.OTP, "token": token})
        self.assertEqual(signature.signature_format, "PAdES-B-T")
        self.assertTrue(signature.timestamped)
        result = verify_pdf(read_version(signature.signed_version, audit=False))[0]
        self.assertTrue(result["valid"])
        self.assertTrue(result["timestamped"])

    def test_web_flow_send_sms_then_sign(self):
        self.login(self.doctor)
        self.client.post(reverse("signatures:credential"), {
            "remote-remote_user_id": FakeCSCService.USER, "remote-password": FakeCSCService.PASSWORD})
        url = reverse("documents:sign", args=[self.document.current_version.pk])
        page = self.client.get(url)
        self.assertContains(page, "Invia OTP via SMS")
        self.assertContains(page, 'name="pin"')
        self.client.post(url, {"action": "send_otp", "password": FakeCSCService.PASSWORD})
        self.assertEqual(self.service.otp_sent, 1)
        page = self.client.get(url)
        self.assertNotContains(page, 'name="password"')  # sessione col prestatore già aperta
        response = self.client.post(url, {"pin": FakeCSCService.PIN, "otp": FakeCSCService.OTP,
                                          "reason": "Relazione", "confirm": "on"})
        self.assertRedirects(response, self.document.get_absolute_url())
        self.assertEqual(self.document.versions.count(), 2)
        self.assertTrue(self.document.current_version.is_signed)

    def test_configuration_check_command(self):
        out = io.StringIO()
        call_command("fasas_firma_verifica", stdout=out)
        self.assertIn("QTSP di prova", out.getvalue())
        self.assertIn("PAdES-B-B", out.getvalue())
