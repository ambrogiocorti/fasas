"""Firma di più documenti in una volta: una passphrase (certificato) o un solo PIN e OTP (firma remota in lotto)."""
from django.test import override_settings
from django.urls import reverse

from fasas.documents.models import Document
from fasas.documents.services import create_document, read_version
from fasas.signatures.models import Signature
from fasas.signatures.providers import SignatureError, verify_pdf
from fasas.signatures.services import register_pkcs12, register_remote, request_otp, sign_versions

from .base import FasasTestCase
from .test_documents import sample_pdf, self_signed_p12
from .test_remote_signature import FakeCSCService


class FirmaMultiplaTest(FasasTestCase):
    def setUp(self):
        self.docs = [create_document(self.guest, Document.Category.PAI, f"PAI {i}", user=self.coordinator,
                                     data=sample_pdf(), filename=f"pai-{i}.pdf") for i in range(3)]

    def versions(self):
        return [d.current_version for d in self.docs]

    def test_certificato_una_passphrase_per_tutti(self):
        register_pkcs12(self.doctor, self_signed_p12("segreta"), "segreta")
        with self.assertRaises(SignatureError):
            sign_versions(self.versions(), self.doctor, "sbagliata")
        self.assertFalse(Signature.objects.exists())  # tutto o niente
        signatures = sign_versions(self.versions(), self.doctor, "segreta", "Approvazione PAI")
        self.assertEqual(len(signatures), 3)
        for signature in signatures:
            result = verify_pdf(read_version(signature.signed_version, audit=False))[0]
            self.assertTrue(result["intact"] and result["valid"])
        self.assertTrue(all(d.current_version.is_signed for d in self.docs))

    def test_pagina_da_firmare_e_firma_dei_selezionati(self):
        register_pkcs12(self.doctor, self_signed_p12("segreta"), "segreta")
        self.login(self.doctor)
        page = self.client.get(reverse("documents:to_sign"))
        self.assertContains(page, "Firma i selezionati")
        chosen = [self.docs[0].current_version.pk, self.docs[2].current_version.pk]
        url = reverse("documents:sign_many")
        page = self.client.get(url, {"v": chosen + [999999]})  # un identificativo estraneo viene ignorato
        self.assertContains(page, "Firma di 2 documenti")
        response = self.client.post(url, {"v": chosen, "passphrase": "segreta", "reason": "PAI",
                                          "confirm": "on"})
        self.assertRedirects(response, reverse("documents:to_sign"))
        self.assertEqual(Signature.objects.count(), 2)
        self.assertFalse(self.docs[1].current_version.is_signed)
        # un documento già firmato non si può riproporre nella firma multipla
        response = self.client.get(url, {"v": chosen})
        self.assertRedirects(response, reverse("documents:to_sign"))
        self.login(self.operator)
        self.assertEqual(self.client.get(url, {"v": [self.docs[1].current_version.pk]}).status_code, 403)


class FirmaRemotaInLottoTest(FasasTestCase):
    def setUp(self):
        self.service = FakeCSCService().__enter__()
        self.settings_override = override_settings(FASAS_CSC_SERVICE_URL=self.service.url, FASAS_CSC_AUTH="basic",
                                                   FASAS_SIGNATURE_TSA_URL="", FASAS_SIGNATURE_LEVEL="")
        self.settings_override.enable()
        self.docs = [create_document(self.guest, Document.Category.MEDICAL_REPORT, f"Relazione {i}",
                                     user=self.coordinator, data=sample_pdf(), filename=f"rel-{i}.pdf")
                     for i in range(3)]

    def tearDown(self):
        self.settings_override.disable()
        self.service.__exit__()

    def secrets(self):
        token = request_otp(self.doctor, FakeCSCService.PASSWORD)
        return {"pin": FakeCSCService.PIN, "otp": FakeCSCService.OTP, "token": token}

    def test_un_solo_pin_e_otp_per_tre_documenti(self):
        self.service.multisign = 5
        credential = register_remote(self.doctor, FakeCSCService.USER, FakeCSCService.PASSWORD)
        self.assertEqual(credential.remote_multisign, 5)
        signatures = sign_versions([d.current_version for d in self.docs], self.doctor, self.secrets(), "Relazioni")
        self.assertEqual(self.service.authorizations, 1)
        self.assertEqual(len(self.service.authorized["sad-1"]), 3)  # tre impronte vincolate alla stessa SAD
        for signature in signatures:
            result = verify_pdf(read_version(signature.signed_version, audit=False))[0]
            self.assertTrue(result["intact"] and result["valid"])

    def test_prestatore_con_una_firma_per_autorizzazione(self):
        register_remote(self.doctor, FakeCSCService.USER, FakeCSCService.PASSWORD)
        with self.assertRaisesMessage(SignatureError, "al massimo 1"):
            sign_versions([d.current_version for d in self.docs[:2]], self.doctor, self.secrets())
        self.assertEqual(self.service.authorizations, 0)
        self.assertFalse(Signature.objects.exists())

    def test_pin_errato_nessuna_firma_salvata(self):
        self.service.multisign = 5
        register_remote(self.doctor, FakeCSCService.USER, FakeCSCService.PASSWORD)
        secrets = {**self.secrets(), "pin": "9999"}
        with self.assertRaisesMessage(SignatureError, "PIN non corretto"):
            sign_versions([d.current_version for d in self.docs], self.doctor, secrets)
        self.assertFalse(Signature.objects.exists())
