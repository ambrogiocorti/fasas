"""Carta di prova: firma con CIE provabile senza lettore, solo nelle installazioni di prova e sempre dichiarata."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from django.core.management import CommandError, call_command
from django.test import LiveServerTestCase, override_settings
from django.urls import reverse

from fasas.accounts.models import Role, User
from fasas.core.models import Community
from fasas.documents.models import Document
from fasas.documents.services import create_document, read_version
from fasas.guests.models import Guest
from fasas.signatures import cie
from fasas.signatures.management.commands.fasas_carta_di_prova import TEST_FISCAL_CODE
from fasas.signatures.models import Signature, SignatureRequest
from fasas.signatures.providers import verify_pdf

from .base import _BACKUP, _MEDIA, FasasTestCase
from .cie_helpers import DeviceClient
from .test_cie_signer_pkcs11 import ON_POSTGRES, SIGNER_DIR, SKIP_PG, ScriptedUI
from .test_documents import sample_pdf

if str(SIGNER_DIR) not in sys.path:
    sys.path.insert(0, str(SIGNER_DIR))


def make_card(folder, username="doc", pin="1234", env_dir=None):
    with override_settings(DEBUG=True, **({"BASE_DIR": env_dir} if env_dir else {})):
        args = ["fasas_carta_di_prova", "--utente", username, "--pin", pin, "--cartella", str(folder)]
        call_command(*args, *([] if env_dir else ["--senza-env"]), stdout=io.StringIO())
    return Path(folder) / f"carta-di-prova-{username}.p12"


class LanStartTests(FasasTestCase):
    def test_lan_start_only_in_test_installations(self):
        from unittest import mock

        from fasas.core.management.commands import fasas_avvia_rete

        with self.assertRaises(CommandError):
            call_command("fasas_avvia_rete", stdout=io.StringIO())
        self.assertTrue(all(ip.startswith(("10.", "172.", "192.168.")) for ip in fasas_avvia_rete.lan_addresses()))
        out = io.StringIO()
        with override_settings(DEBUG=True), \
                mock.patch.object(fasas_avvia_rete, "lan_addresses", return_value=["192.168.1.20"]), \
                mock.patch.object(fasas_avvia_rete, "call_command") as runserver, \
                mock.patch.dict("os.environ", {}):
            call_command("fasas_avvia_rete", stdout=out)
            import os

            self.assertEqual(os.environ["DJANGO_ALLOWED_HOSTS"], "localhost,127.0.0.1,192.168.1.20")
        runserver.assert_called_once_with("runserver", "0.0.0.0:8000")
        self.assertIn("http://192.168.1.20:8000/", out.getvalue())


class TestCardCommandTests(FasasTestCase):
    def test_only_in_test_installations(self):
        with self.assertRaises(CommandError):
            call_command("fasas_carta_di_prova", "--utente", "doc", "--senza-env", stdout=io.StringIO())

    def test_creates_card_ca_and_env(self):
        folder, env_dir = tempfile.mkdtemp(), tempfile.mkdtemp()
        (Path(env_dir) / ".env").write_text("DJANGO_DEBUG=1", encoding="utf-8")
        card = make_card(folder, env_dir=Path(env_dir))
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.fiscal_code, TEST_FISCAL_CODE)  # mancava: impostato quello fittizio
        key, cert, extra = pkcs12.load_key_and_certificates(card.read_bytes(), b"1234")
        self.assertEqual(cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value, TEST_FISCAL_CODE)
        self.assertIn("SOLO PROVA", cert.issuer.rfc4514_string())
        self.assertEqual(card.with_suffix(".cer").read_bytes(), cert.public_bytes(__import__(
            "cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.DER))
        with self.assertRaises(ValueError):
            pkcs12.load_key_and_certificates(card.read_bytes(), b"0000")
        env = (Path(env_dir) / ".env").read_text(encoding="utf-8")
        self.assertIn("DJANGO_DEBUG=1\n", env)
        self.assertIn("FASAS_CIE_TRUST_ROOTS=", env)
        make_card(folder, username="coord", env_dir=Path(env_dir))  # stessa CA, .env non duplicato
        self.assertEqual((Path(env_dir) / ".env").read_text(encoding="utf-8").count("FASAS_CIE_TRUST_ROOTS"), 1)
        self.assertEqual(len(list(Path(folder).glob("ca-radice.pem"))), 1)


@unittest.skipIf(ON_POSTGRES, SKIP_PG)
@override_settings(MEDIA_ROOT=_MEDIA, FASAS_BACKUP_DIR=Path(_BACKUP), FASAS_ALLOWED_NETWORKS=[],
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], FASAS_CIE_REVOCATION="off",
                   FASAS_CIE_ALLOW_HTTP=True, FASAS_SIGNATURE_TSA_URL="")
class TestCardSignerTests(LiveServerTestCase):
    def setUp(self):
        call_command("fasas_setup", stdout=io.StringIO())
        self.doctor = User(username="doc", role=Role.DOCTOR, first_name="Laura", last_name="Bianchi")
        self.doctor.set_password("x")
        self.doctor.save()
        guest = Guest.objects.create(community=Community.default(), fiscal_code="RSSMRA80A01F205X", first_name="Mario",
                                     last_name="Rossi", birth_date="1980-01-01", admission_date="2026-01-01")
        self.document = create_document(guest, Document.Category.MEDICAL_REPORT, "Relazione", user=self.doctor,
                                        data=sample_pdf(), filename="relazione.pdf")
        self.folder = Path(tempfile.mkdtemp())
        self.card = make_card(self.folder)
        trust = {"FASAS_CIE_TRUST_ROOTS": str(self.folder / "ca-radice.pem"),
                 "FASAS_CIE_INTERMEDIATES": str(self.folder / "ca-intermedia.pem")}
        self.settings_override = override_settings(DEBUG=True, **trust)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def service(self, pins, server=None):
        from fasas_signer.card import make_card as signer_card
        from fasas_signer.client import ServerClient
        from fasas_signer.engine import Service

        client = ServerClient(self.live_server_url, allow_http=True)
        client.pair(cie.create_pairing(self.doctor), "PC senza lettore", "windows")
        card = signer_card({"carta_di_prova": str(self.card), "server": server or self.live_server_url})
        ui = ScriptedUI(pins)
        return Service(client, card, ui), ui

    def test_signs_with_wrong_then_right_pin_and_is_labelled(self):
        self.doctor.refresh_from_db()
        request = cie.create_request(self.document.current_version, self.doctor, "Prova senza lettore")
        service, ui = self.service(["0000", "1234"])
        service.report_status()
        service.run(once=True)
        self.assertEqual(ui.results[0][0], "done", ui.results)
        self.assertTrue(any(kind == "pin" and text and "PIN errato" in text for kind, text in ui.messages))
        request.refresh_from_db()
        self.assertTrue(request.is_test_card)
        signature = Signature.objects.get()
        self.assertEqual((signature.provider, signature.legal_level), ("cie-prova", ""))
        self.assertIn("CARTA DI PROVA", signature.signed_version.note)
        [result] = verify_pdf(read_version(signature.signed_version))
        self.assertTrue(result["intact"] and result["valid"])
        self.assertIn("Nessun lettore", str(request.device.status["readers"]))
        self.client.force_login(self.doctor)
        self.assertContains(self.client.get(self.document.get_absolute_url()), "carta di prova – nessun valore legale")
        self.assertTrue(self.client.get(reverse("signatures:cie_status", args=[request.pk])).json()["test_card"])

    def test_refused_outside_test_installations_and_remote_servers(self):
        from fasas_signer.card import CardError

        with self.assertRaises(CardError):
            self.service(["1234"], server="https://fasas.esempio.it/")
        self.doctor.refresh_from_db()
        request = cie.create_request(self.document.current_version, self.doctor)
        service, ui = self.service(["1234"])
        with override_settings(DEBUG=False):
            service.run(once=True)
        request.refresh_from_db()
        self.assertEqual((request.status, request.error_code), ("failed", "cert_untrusted"))
        self.assertFalse(Signature.objects.exists())

    def test_three_wrong_pins_block_the_test_card(self):
        self.doctor.refresh_from_db()
        request = cie.create_request(self.document.current_version, self.doctor)
        service, ui = self.service(["1111", "2222", "3333"])
        service.run(once=True)
        request.refresh_from_db()
        self.assertEqual((request.status, request.error_code), ("failed", "pin_blocked"))
        self.assertEqual(SignatureRequest.objects.get().pin_attempts_left, 0)

    def test_device_api_test_card_status_is_honest(self):
        device = DeviceClient(self.client_class())
        device.pair(cie.create_pairing(self.doctor))
        from fasas_signer.test_card import TestCard

        status = TestCard(self.card).status()
        self.assertIn("non è una CIE", status["middleware"])
        self.assertEqual(device.post("dispositivo/stato/", status)[0], 200)
