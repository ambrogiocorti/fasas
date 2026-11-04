"""
Verifica con CIE per aprire, scaricare o modificare i documenti (Configurazione generale, spenta per default).

La carta firma una sfida casuale del server con la sua chiave: si controlla che il certificato sia emesso dalle CA
configurate e intestato all'utente (codice fiscale). Le «carte» sono chiavi e certificati di prova (cie_helpers):
il collaudo con una CIE reale sul telefono resta da fare.
"""
import datetime
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.core.forms import SystemConfigForm
from fasas.core.models import SystemConfig
from fasas.documents.models import Document
from fasas.documents.services import add_version, create_document
from fasas.signatures import cie
from fasas.signatures.models import CieAccess, SignatureRequest
from fasas.signatures.providers import SignatureError

from .base import FasasTestCase
from .cie_helpers import DeviceClient, TestPKI
from .test_documents import sample_pdf

PKI = TestPKI("Accesso")
OPERATOR_CF = "RSSLGU80A01F205X"
OTHER_CF = "VRDGPP75C10F205K"


@override_settings(**PKI.settings(FASAS_CIE_ENABLED=True))
class CieDocumentAccessTests(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.operator.fiscal_code = OPERATOR_CF
        cls.operator.save()
        cls.card = PKI.card(OPERATOR_CF, "Olga", "Operatrice")

    def setUp(self):
        cache.clear()
        self.document = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione clinica",
                                        user=self.doctor, data=sample_pdf(), filename="relazione.pdf")
        self.other = create_document(self.guest, Document.Category.CONSENT, "Consenso informato",
                                     user=self.doctor, data=sample_pdf(), filename="consenso.pdf")
        self.set_gate(True)

    def set_gate(self, on, minutes=10):
        config = SystemConfig.get()
        config.documents_cie_required, config.documents_cie_minutes = on, minutes
        config.save()

    def urls(self, document):
        version = document.current_version
        return [reverse("documents:detail", args=[document.pk]), reverse("documents:view", args=[version.pk]),
                reverse("documents:download", args=[version.pk])]

    def assert_gated(self, url, document=None):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302, url)
        target = urlparse(response["Location"])
        self.assertEqual(target.path, reverse("signatures:cie_access"))
        query = parse_qs(target.query)
        self.assertEqual(query["next"], [url])
        if document is not None:
            self.assertEqual(query["documento"], [str(document.pk)])

    def verify(self, card=None, document=None, next_url=None):
        """Flusso completo: pagina di verifica, richiesta, telefono (presa in carico, carta, PIN, firma della sfida)."""
        document = document or self.document
        device = DeviceClient(self.client_class())
        status, data = device.pair(cie.create_pairing(self.operator), "Telefono", "android")
        self.assertEqual(status, 201, data)
        next_url = next_url or reverse("documents:view", args=[document.current_version.pk])
        page = self.client.get(reverse("signatures:cie_access"), {"documento": document.pk, "next": next_url})
        self.assertContains(page, "Verifica con CIE")
        response = self.client.post(reverse("signatures:cie_access"), {"documento": document.pk, "next": next_url})
        request = SignatureRequest.objects.get(user=self.operator, purpose=SignatureRequest.Purpose.ACCESS,
                                               access_document=document, status="waiting")
        self.assertRedirects(response, reverse("signatures:cie_request", args=[request.pk]))
        status, pending = device.get("richieste/?attesa=0")
        self.assertEqual(pending["requests"][0]["purpose"], "access")
        self.assertEqual(pending["requests"][0]["title"], document.title)
        return request, device.sign_flow(request.pk, card or self.card)

    def test_off_by_default(self):
        self.set_gate(False)
        self.assertFalse(SystemConfig._meta.get_field("documents_cie_required").default)
        self.login(self.operator)
        for url in self.urls(self.document):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_every_document_page_needs_the_cie_even_when_signed(self):
        signed = add_version(self.document, sample_pdf(), "relazione_firmata.pdf", self.doctor,
                             content_type="application/pdf", is_signed=True, note="firmato")
        self.assertTrue(self.document.current_version.is_signed)
        self.login(self.operator)
        for url in self.urls(self.document):
            self.assert_gated(url, self.document)
        self.login(self.coordinator)
        self.assert_gated(reverse("documents:edit", args=[self.document.pk]), self.document)
        self.assert_gated(reverse("documents:version_upload", args=[self.document.pk]), self.document)
        self.login(self.doctor)
        self.assert_gated(reverse("documents:verify", args=[signed.pk]), self.document)
        self.assert_gated(reverse("documents:sign_cie", args=[signed.pk]), self.document)

    def test_verification_opens_only_that_document_for_a_few_minutes(self):
        self.login(self.operator)
        next_url = reverse("documents:view", args=[self.document.current_version.pk])
        request, (status, data) = self.verify(next_url=next_url)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["verification"]["level"], "Verifica di identità")
        self.assertIsNone(data["version"])  # nessuna nuova versione: non è la firma del documento
        request.refresh_from_db()
        self.assertEqual(request.status, SignatureRequest.Status.SIGNED)
        state = self.client.get(reverse("signatures:cie_status", args=[request.pk])).json()
        self.assertEqual(state["label"], "Identità verificata")
        self.assertEqual(state["result_url"], next_url)
        for url in self.urls(self.document):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assert_gated(reverse("documents:view", args=[self.other.current_version.pk]), self.other)
        self.assertEqual(self.document.versions.count(), 1)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.PERMISSION,
                                                object_repr="Accesso ai documenti verificato con CIE").exists())
        # scaduto il tempo, si verifica di nuovo
        CieAccess.objects.update(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        self.assert_gated(next_url, self.document)

    def test_card_of_another_person_or_missing_fiscal_code(self):
        self.login(self.operator)
        request, (status, data) = self.verify(card=PKI.card(OTHER_CF, "Giuseppe", "Verdi"))
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "cert_mismatch")
        self.assertFalse(CieAccess.objects.exists())
        self.assert_gated(reverse("documents:view", args=[self.document.current_version.pk]))
        # carta di una CA non della CIE
        _, (status, data) = self.verify(card=TestPKI("Estranea").card(OPERATOR_CF))
        self.assertEqual(status, 400)
        self.assertFalse(CieAccess.objects.exists())
        self.operator.fiscal_code = ""
        self.operator.save()
        with self.assertRaises(SignatureError):
            cie.create_access_request(self.operator, self.guest, self.document)

    def test_bad_parameters_and_foreign_next(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("signatures:cie_access"), {"documento": "x"}).status_code, 404)
        page = self.client.get(reverse("signatures:cie_access"),
                               {"documento": self.document.pk, "next": "https://altro.esempio.it/"})
        self.assertContains(page, f'name="next" value="{self.document.get_absolute_url()}"')

    def test_access_only_users_cannot_sign_documents(self):
        self.assertFalse(self.operator.has_perm(cie.PERMISSION))
        self.assertTrue(cie.can_use_device(self.operator))
        with self.assertRaises(SignatureError):
            cie.create_request(self.document.current_version, self.operator, "prova")
        self.set_gate(False)
        self.assertFalse(cie.can_use_device(self.operator))  # verifica spenta: niente telefono per chi non firma

    def test_export_with_documents_needs_the_cie(self):
        self.login(self.coordinator)
        url = reverse("reports:guest_export", args=[self.guest.pk])
        response = self.client.post(url, {"include_documents": "on"})
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        self.assertIn(f"ospite={self.guest.pk}", response["Location"])
        response = self.client.post(url, {"include_documents": ""})  # senza documenti allegati non serve
        self.assertEqual(response.status_code, 302, response.content.decode()[-3000:])
        self.assertIn("/report/", response["Location"])

    def test_configuration_requires_cie_on_the_server(self):
        config = SystemConfig.get()
        config.documents_cie_required = False
        config.save()
        data = {f.name: getattr(config, f.name) for f in SystemConfig._meta.fields if f.name not in ("id", "community", "updated_at")}
        data["documents_cie_required"] = True
        with override_settings(FASAS_CIE_ENABLED=False):
            form = SystemConfigForm(data, instance=config)
            self.assertFalse(form.is_valid())
            self.assertIn("documents_cie_required", form.errors)
        form = SystemConfigForm(data, instance=config)
        self.assertTrue(form.is_valid(), form.errors)
