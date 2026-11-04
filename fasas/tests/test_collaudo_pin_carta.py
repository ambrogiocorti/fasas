"""Firma con il PIN della carta disponibile solo dopo una firma di prova riuscita con una CIE vera."""
from django.test import override_settings
from django.urls import reverse

from fasas.core.models import SystemConfig
from fasas.signatures import cie
from fasas.signatures.models import SignatureRequest
from fasas.signatures.providers import SignatureError

from .base import FasasTestCase


@override_settings(FASAS_CIE_PIN_REQUIRES_TEST=True, FASAS_CIE_ENABLED=True)
class CardPinTestGateTests(FasasTestCase):
    def make_test_signature(self, issuer="CN=Ministero dell'Interno, O=CA del Ministero dell'Interno", trusted=True):
        request = cie._base_request(self.doctor, reason="Prova", purpose=SignatureRequest.Purpose.TEST,
                                    version_sha256="0" * 64)
        request.status = SignatureRequest.Status.SIGNED
        request.certificate_issuer = issuer
        request.verification = {"trusted": trusted, "intact": True, "valid": True}
        request.save()
        return request

    def test_not_tested_by_default(self):
        self.assertFalse(cie.card_pin_tested())
        with self.assertRaises(SignatureError) as ctx:
            cie.create_acceptance_request(self.doctor)
        self.assertEqual(ctx.exception.code, "not_tested")

    def test_untrusted_or_test_card_does_not_count(self):
        self.make_test_signature(trusted=False)
        self.make_test_signature(issuer="CN=CIE di prova - SOLO PROVA")
        self.assertFalse(cie.card_pin_tested())

    def test_real_test_signature_unlocks(self):
        self.make_test_signature()
        self.assertTrue(cie.card_pin_tested())

    def test_access_methods_and_config(self):
        config = SystemConfig.get()
        config.documents_verification = "nis"
        config.save()
        self.assertEqual(cie.access_methods(), ["nis"])
        self.make_test_signature()
        self.assertEqual(cie.access_methods(), ["nis", "cie"])

    def test_credential_page_says_so(self):
        self.login(self.doctor)
        self.assertContains(self.client.get(reverse("signatures:credential")), "Firma con il PIN della carta da collaudare")
        self.make_test_signature()
        self.assertNotContains(self.client.get(reverse("signatures:credential")),
                               "Firma con il PIN della carta da collaudare")
