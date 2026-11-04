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
from fasas.signatures.models import CieAccess, CieEnrollment, SignatureRequest
from fasas.signatures.providers import SignatureError

from .base import FasasTestCase
from .cie_helpers import DeviceClient, TestCSCA, TestPKI
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
        config.documents_verification = "cie"  # qui: la CIE con il suo PIN (il PIN FASAS è in CieWithoutPinTests)
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
        config.documents_verification = "cie"
        data = {f.name: getattr(config, f.name) for f in SystemConfig._meta.fields if f.name not in ("id", "community", "updated_at")}
        data["documents_cie_required"] = True
        with override_settings(FASAS_CIE_ENABLED=False):
            form = SystemConfigForm(data, instance=config)
            self.assertFalse(form.is_valid())
            self.assertIn("documents_cie_required", form.errors)
        form = SystemConfigForm(data, instance=config)
        self.assertTrue(form.is_valid(), form.errors)


CSCA = TestCSCA()


@override_settings(**PKI.settings(FASAS_CIE_ENABLED=True, FASAS_CIE_CSCA=CSCA.path))
class CieWithoutPinTests(FasasTestCase):
    """CIE appoggiata al telefono + PIN FASAS al posto del PIN della carta (protocollo NIS del Ministero)."""

    def setUp(self):
        cache.clear()
        self.document = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione clinica",
                                        user=self.doctor, data=sample_pdf(), filename="relazione.pdf")
        config = SystemConfig.get()
        config.documents_cie_required, config.documents_verification = True, "nis"
        config.save()
        self.card = CSCA.card()
        self.login(self.operator)  # nessun codice fiscale: con la CIE senza PIN non serve
        self.phone = DeviceClient(self.client_class())
        status, data = self.phone.pair(cie.create_pairing(self.operator), "Telefono", "android")
        self.assertEqual(status, 201, data)

    def run_request(self, request_id, card=None, **payload):
        status, claimed = self.phone.post(f"richieste/{request_id}/prendi/")
        self.assertEqual(status, 200, claimed)
        self.assertEqual(claimed["method"], "nis")
        data = (card or self.card).payload(claimed["challenge"], **payload)
        return claimed, self.phone.post(f"richieste/{request_id}/cie-senza-pin/", {"nonce": claimed["nonce"], **data})

    def enroll(self, card=None):
        response = self.client.post(reverse("signatures:credential"), {"action": "cie-enroll"})
        request = SignatureRequest.objects.filter(user=self.operator, purpose="enroll").latest("created_at")
        self.assertRedirects(response, reverse("signatures:cie_request", args=[request.pk]))
        return self.run_request(request.pk, card, with_sod=True)[1]

    def set_pin(self, pin="482913", old=None):
        data = {"action": "fasas-pin", "pin": pin, "pin2": pin}
        if old:
            data["old_pin"] = old
        return self.client.post(reverse("signatures:credential"), data, follow=True)

    def start_access(self):
        url = reverse("documents:view", args=[self.document.current_version.pk])
        response = self.client.post(reverse("signatures:cie_access"),
                                    {"documento": self.document.pk, "next": url, "metodo": "nis"})
        request = SignatureRequest.objects.filter(user=self.operator, purpose="access").latest("created_at")
        self.assertRedirects(response, reverse("signatures:cie_request", args=[request.pk]))
        return request, url

    def ready(self):
        status, data = self.enroll()
        self.assertEqual(status, 200, data)
        self.set_pin()
        enrollment = CieEnrollment.objects.get(user=self.operator)
        cie.confirm_enrollment(enrollment, self.admin)
        return enrollment

    def test_first_access_then_card_and_fasas_pin_open_the_document(self):
        status, data = self.enroll()
        self.assertEqual(status, 200, data)
        enrollment = CieEnrollment.objects.get(user=self.operator)
        self.assertFalse(enrollment.is_confirmed)
        self.assertNotIn(self.card.nis.decode(), str(enrollment.__dict__))  # del NIS si conserva solo l'impronta
        page = self.set_pin("111111")
        self.assertContains(page, "troppo facile")
        page = self.set_pin("482913")
        self.assertContains(page, "PIN FASAS salvato")
        enrollment.refresh_from_db()
        self.assertNotIn("482913", enrollment.pin_hash)
        # senza la conferma dell'amministratore non si apre nulla
        page = self.client.post(reverse("signatures:cie_access"), {"documento": self.document.pk, "metodo": "nis"})
        self.assertContains(page, "conferma dell")
        with self.assertRaises(SignatureError):
            cie.confirm_enrollment(enrollment, self.operator)  # non si conferma da sé
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("accounts:user_list")), "da confermare")
        self.client.post(reverse("signatures:enrollment_action", args=[enrollment.pk]), {"action": "confirm"})
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.ready)
        # apertura: PIN FASAS sbagliato, poi giusto (stessa richiesta, nessun nuovo appoggio della carta)
        self.login(self.operator)
        request, url = self.start_access()
        claimed, (status, data) = self.run_request(request.pk, pin="000001")
        self.assertEqual((status, data["error"], data["attempts_left"]), (400, "pin_wrong", 4))
        payload = self.card.payload(claimed["challenge"], pin="482913")
        status, data = self.phone.post(f"richieste/{request.pk}/cie-senza-pin/", {"nonce": claimed["nonce"], **payload})
        self.assertEqual(status, 200, data)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(CieAccess.objects.get().method, "nis")
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.pin_failures, 0)
        # la stessa risposta non si riusa
        status, data = self.phone.post(f"richieste/{request.pk}/cie-senza-pin/", {"nonce": claimed["nonce"], **payload})
        self.assertNotEqual(status, 200)

    def test_another_card_a_clone_or_a_foreign_sod_are_refused(self):
        self.ready()
        request, url = self.start_access()
        _, (status, data) = self.run_request(request.pk, CSCA.card(), pin="482913")
        self.assertEqual((status, data["error"]), (400, "cert_mismatch"))
        # clone: stesso NIS e stessa chiave pubblica, ma senza la chiave privata del chip
        request, url = self.start_access()
        _, (status, data) = self.run_request(request.pk, pin="482913", response=bytes(256))
        self.assertEqual((status, data["error"]), (400, "bad_signature"))
        self.assertFalse(CieAccess.objects.exists())
        # registrazione con una carta firmata da un Document Signer non della CSCA configurata
        CieEnrollment.objects.update(revoked_at=timezone.now())
        foreign = TestCSCA("Estranea").card()
        status, data = self.enroll(foreign)
        self.assertEqual((status, data["error"]), (400, "cert_untrusted"))

    def test_pin_lockout_and_reset_by_the_administrator(self):
        enrollment = self.ready()
        request, _ = self.start_access()
        claimed, (status, data) = self.run_request(request.pk, pin="999990")
        for _attempt in range(CieEnrollment.MAX_PIN_FAILURES - 1):  # stessa richiesta, si riprova il PIN
            payload = self.card.payload(claimed["challenge"], pin="999990")
            status, data = self.phone.post(f"richieste/{request.pk}/cie-senza-pin/",
                                           {"nonce": claimed["nonce"], **payload})
            self.assertEqual(status, 400)
        self.assertEqual(data["error"], "pin_blocked")
        request.refresh_from_db()
        self.assertEqual(request.status, SignatureRequest.Status.FAILED)
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.pin_locked)
        page = self.client.post(reverse("signatures:cie_access"), {"documento": self.document.pk, "metodo": "nis"})
        self.assertContains(page, "bloccato")
        self.login(self.admin)
        self.client.post(reverse("signatures:enrollment_action", args=[enrollment.pk]), {"action": "revoke"})
        enrollment.refresh_from_db()
        self.assertIsNotNone(enrollment.revoked_at)

    def test_computers_do_not_receive_requests_without_card_pin(self):
        computer = DeviceClient(self.client_class())
        computer.pair(cie.create_pairing(self.operator), "PC", "windows")
        self.client.post(reverse("signatures:credential"), {"action": "cie-enroll"})
        status, pending = computer.get("richieste/?attesa=0")
        self.assertEqual(pending["requests"], [])
        status, pending = self.phone.get("richieste/?attesa=0")
        self.assertEqual(pending["requests"][0]["purpose"], "enroll")

    def test_one_card_one_person(self):
        self.ready()
        other_phone = DeviceClient(self.client_class())
        other_phone.pair(cie.create_pairing(self.coordinator), "Telefono 2", "android")
        request = cie.create_enroll_request(self.coordinator)
        self.phone = other_phone
        _, (status, data) = self.run_request(request.pk, with_sod=True)
        self.assertEqual((status, data["error"]), (400, "card_in_use"))

    def test_the_card_pin_still_works_and_signing_still_needs_it(self):
        page = self.client.get(reverse("signatures:cie_access"), {"documento": self.document.pk})
        self.assertContains(page, "Verifica con CIE e PIN FASAS")
        self.assertContains(page, "Verifica con il PIN della carta")
        self.assertEqual(cie.access_methods(), ["nis", "cie"])
        with self.assertRaises(SignatureError):  # la firma dei documenti non cambia: CIE con il suo PIN
            cie.create_request(self.document.current_version, self.operator, "prova")
