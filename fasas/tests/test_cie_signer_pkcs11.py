"""
FASAS Signer contro un server FASAS in ascolto, con un modulo PKCS#11 reale (SoftHSM2).

La chiave RSA viene generata dentro il token SoftHSM e non ne esce mai, come nella CIE; il certificato è
emesso da una CA di prova con un codice fiscale di prova. È un collaudo del protocollo, del Signer e del
motore PAdES con PKCS#11 vero: NON è un collaudo con una CIE, che resta da fare su un dispositivo reale.
Il test si salta se SoftHSM2 o python-pkcs11 non sono installati.
"""
import base64
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import LiveServerTestCase, override_settings

from fasas.accounts.models import Role, User
from fasas.core.models import Community
from fasas.documents.models import Document
from fasas.documents.services import create_document, read_version
from fasas.guests.models import Guest
from fasas.signatures import cie
from fasas.signatures.models import LegalLevel, Signature, SignatureRequest
from fasas.signatures.providers import verify_pdf

from .base import _BACKUP, _MEDIA
from .cie_helpers import TestPKI, record_acceptance
from .test_documents import sample_pdf

SIGNER_DIR = Path(__file__).resolve().parents[2] / "signer"
SOFTHSM_LIBS = ["/usr/lib/softhsm/libsofthsm2.so", "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
                "/usr/local/lib/softhsm/libsofthsm2.so", "/opt/homebrew/lib/softhsm/libsofthsm2.so"]
SOFTHSM_LIB = next((p for p in SOFTHSM_LIBS if os.path.exists(p)), "")
PIN, SO_PIN, CF = "5678", "87654321", "BNCLRA80A41H501Y"
PKI = TestPKI("SoftHSM")

try:
    import pkcs11  # noqa: F401
    HAVE_PKCS11 = bool(SOFTHSM_LIB and shutil.which("softhsm2-util"))
except ImportError:
    HAVE_PKCS11 = False

# Il server in ascolto richiede di svuotare le tabelle tra un test e l'altro: su PostgreSQL i trigger dell'audit
# append-only lo impediscono (giustamente), quindi questi test girano su SQLite (anche nella CI).
ON_POSTGRES = connection.vendor == "postgresql"
SKIP_PG = "su PostgreSQL l'audit append-only impedisce lo svuotamento tra i test con server in ascolto"

if str(SIGNER_DIR) not in sys.path:
    sys.path.insert(0, str(SIGNER_DIR))


def init_token(directory):
    """Token «CIE0» con chiave RSA 2048 generata nel token e certificato di prova associato (stesso CKA_ID)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import Encoding
    from pkcs11 import Attribute, CertificateType, KeyType, ObjectClass

    conf = Path(directory) / "softhsm2.conf"
    (Path(directory) / "tokens").mkdir()
    conf.write_text(f"directories.tokendir = {directory}/tokens\nobjectstore.backend = file\nlog.level = ERROR\n")
    os.environ["SOFTHSM2_CONF"] = str(conf)
    subprocess.run(["softhsm2-util", "--init-token", "--free", "--label", "CIE0", "--so-pin", SO_PIN, "--pin", PIN],
                   check=True, capture_output=True)
    lib = pkcs11.lib(SOFTHSM_LIB)
    token = lib.get_token(token_label="CIE0")
    with token.open(rw=True, user_pin=PIN) as session:
        public, _ = session.generate_keypair(KeyType.RSA, 2048, id=b"CIE0", label="CIE0", store=True)
        numbers = rsa.RSAPublicNumbers(int.from_bytes(public[Attribute.PUBLIC_EXPONENT], "big"),
                                       int.from_bytes(public[Attribute.MODULUS], "big"))
        card = PKI.card(CF, key=_PublicOnly(numbers.public_key()))
        session.create_object({Attribute.CLASS: ObjectClass.CERTIFICATE, Attribute.CERTIFICATE_TYPE: CertificateType.X_509,
                               Attribute.TOKEN: True, Attribute.ID: b"CIE0", Attribute.LABEL: "CIE0",
                               Attribute.SUBJECT: card.cert.subject.public_bytes(),
                               Attribute.ISSUER: card.cert.issuer.public_bytes(),
                               Attribute.VALUE: card.cert.public_bytes(Encoding.DER)})
    return card.cert


class _PublicOnly:
    """Per costruire il certificato serve solo la chiave pubblica: quella privata resta nel token."""

    def __init__(self, public_key):
        self._public = public_key

    def public_key(self):
        return self._public


class ScriptedUI:
    """Utente simulato del Signer: conferma e digita i PIN indicati (il primo può essere sbagliato)."""

    def __init__(self, pins, confirm=True):
        self.pins, self.confirmed, self.messages, self.results = list(pins), confirm, [], []

    def confirm(self, request):
        self.messages.append(("confirm", request["verify_code"]))
        return self.confirmed

    def ask_pin(self, request, message=None):
        self.messages.append(("pin", message))
        return self.pins.pop(0) if self.pins else None

    def info(self, text):
        self.messages.append(("info", text))

    def done(self, request, result):
        self.results.append(("done", result))

    def failed(self, request, message):
        self.results.append(("failed", message))


@unittest.skipUnless(HAVE_PKCS11, "SoftHSM2 o python-pkcs11 non installati")
@unittest.skipIf(ON_POSTGRES, SKIP_PG)
@override_settings(MEDIA_ROOT=_MEDIA, FASAS_BACKUP_DIR=Path(_BACKUP), FASAS_ALLOWED_NETWORKS=[],
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], **PKI.settings())
class SignerPkcs11Tests(LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hsm_dir = tempfile.mkdtemp(prefix="fasas-softhsm-")
        cls.token_cert = init_token(cls.hsm_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.hsm_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from fasas_signer.client import ServerClient

        call_command("fasas_setup", stdout=io.StringIO())
        self.doctor = User(username="medico", role=Role.DOCTOR, first_name="Laura", last_name="Bianchi",
                           fiscal_code=CF)
        self.doctor.set_password("x")
        self.doctor.save()
        record_acceptance(self.doctor)
        guest = Guest.objects.create(community=Community.default(), fiscal_code="RSSMRA80A01F205X", first_name="Mario",
                                     last_name="Rossi", birth_date="1980-01-01", admission_date="2026-01-01")
        self.document = create_document(guest, Document.Category.MEDICAL_REPORT, "Relazione", user=self.doctor,
                                        data=sample_pdf(), filename="relazione.pdf")
        self.client_api = ServerClient(self.live_server_url, allow_http=True)
        self.client_api.pair(cie.create_pairing(self.doctor), "PC di prova", "linux")

    def service(self, ui, library=SOFTHSM_LIB):
        from fasas_signer.card import Pkcs11Card
        from fasas_signer.engine import Service

        service = Service(self.client_api, Pkcs11Card(library), ui)
        service.engine.card_wait = 2
        return service

    def test_real_pkcs11_signature_with_wrong_pin_first(self):
        request = cie.create_request(self.document.current_version, self.doctor, "Prova PKCS#11")
        ui = ScriptedUI(["0000", PIN])
        service = self.service(ui)
        service.report_status()
        service.run(once=True)
        self.assertEqual(ui.results[0][0], "done", ui.results)
        self.assertIn(("pin", None), ui.messages)
        self.assertTrue(any(kind == "pin" and text and "PIN errato" in text for kind, text in ui.messages))
        request.refresh_from_db()
        self.assertEqual(request.status, "signed")
        signature = Signature.objects.get()
        self.assertEqual((signature.provider, signature.legal_level), ("cie", LegalLevel.FEA))
        signed = read_version(signature.signed_version)
        [result] = verify_pdf(signed)
        self.assertTrue(result["intact"] and result["valid"] and result["trusted"] and result["covers_whole_document"])
        self.assertIn(CF, result["signer"])
        # Il PIN non arriva mai al server: nel database non c'è traccia
        device = request.device
        self.assertTrue(device.status["middleware_found"])
        binary = {"certificate", "prepared", "nonce_hash", "version_sha256", "certificate_fingerprint",
                  "certificate_serial", "certificate_subject", "id", "created_at", "updated_at", "expires_at",
                  "completed_at", "verification"}
        texts = [str(v) for row in SignatureRequest.objects.values() for k, v in row.items() if k not in binary]
        self.assertNotIn(PIN, " ".join(texts) + str(device.status))
        self.assertEqual(base64.b64decode(request.certificate), self.token_cert.public_bytes(
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.DER))

    def test_user_refuses_and_cancels_pin(self):
        refused = cie.create_request(self.document.current_version, self.doctor)
        self.service(ScriptedUI([], confirm=False)).run(once=True)
        refused.refresh_from_db()
        self.assertEqual((refused.status, refused.error_code), ("cancelled", "cancelled"))
        request = cie.create_request(self.document.current_version, self.doctor)
        ui = ScriptedUI([])  # nessun PIN: l'utente annulla alla richiesta del PIN
        self.service(ui).run(once=True)
        request.refresh_from_db()
        self.assertEqual((request.status, request.error_code), ("cancelled", "cancelled"))
        self.assertFalse(Signature.objects.exists())

    def test_missing_middleware_is_reported(self):
        request = cie.create_request(self.document.current_version, self.doctor)
        ui = ScriptedUI([PIN])
        self.service(ui, library="/percorso/inesistente/libcie-pkcs11.so").run(once=True)
        request.refresh_from_db()
        self.assertEqual((request.status, request.error_code), ("failed", "middleware_missing"))
        self.assertEqual(ui.results[0][0], "failed")


class FakeCard:
    """Carta finta solo per i casi di errore del lettore (nessuna firma viene prodotta)."""

    def __init__(self, present=True, sign_error=None, cert=None):
        self.present, self.sign_error, self.cert = present, sign_error, cert

    def status(self):
        return {"middleware_found": True, "readers": ["Lettore di prova"], "card_present": self.present}

    def card_present(self):
        return self.present

    def certificate(self):
        from cryptography.hazmat.primitives.serialization import Encoding

        return self.cert.public_bytes(Encoding.DER)

    def sign(self, pin, to_be_signed, digest_info, on_login=None):
        on_login()
        raise self.sign_error


@unittest.skipIf(ON_POSTGRES, SKIP_PG)
@override_settings(MEDIA_ROOT=_MEDIA, FASAS_BACKUP_DIR=Path(_BACKUP), FASAS_ALLOWED_NETWORKS=[],
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], **PKI.settings())
class SignerEngineErrorTests(LiveServerTestCase):
    setUp = SignerPkcs11Tests.setUp

    def run_with(self, card):
        from fasas_signer.engine import Service

        request = cie.create_request(self.document.current_version, self.doctor)
        ui = ScriptedUI([PIN])
        service = Service(self.client_api, card, ui)
        service.engine.card_wait = 1
        service.run(once=True)
        request.refresh_from_db()
        return request, ui

    def test_card_absent_and_removed(self):
        from fasas_signer.card import CardError

        request, ui = self.run_with(FakeCard(present=False))
        self.assertEqual((request.status, request.error_code), ("failed", "card_absent"))
        self.assertIn(("info", "Appoggia la CIE sul lettore e tienila ferma."), ui.messages)
        card = FakeCard(cert=PKI.card(CF).cert, sign_error=CardError("card_removed", "Carta allontanata."))
        request, ui = self.run_with(card)
        self.assertEqual((request.status, request.error_code), ("failed", "card_removed"))
        self.assertEqual(ui.results[0][0], "failed")

    def test_pin_blocked(self):
        from fasas_signer.card import CardError

        card = FakeCard(cert=PKI.card(CF).cert, sign_error=CardError("pin_blocked", "PIN bloccato.", 0))
        request, _ = self.run_with(card)
        self.assertEqual((request.status, request.error_code, request.pin_attempts_left), ("failed", "pin_blocked", 0))

    def test_https_required_for_remote_servers(self):
        from fasas_signer.client import ServerClient

        with self.assertRaises(ValueError):
            ServerClient("http://fasas.esempio.it/")
        self.assertTrue(ServerClient("https://fasas.esempio.it/").base.startswith("https://"))
