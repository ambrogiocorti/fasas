"""Modulistica: moduli predefiniti, modifica e versioni, distribuzione, compilazione online, PDF, firmato, revoca."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfReader

from fasas.accounts.models import Role
from fasas.documents.models import Document
from fasas.modulistica import services
from fasas.modulistica.models import FormAssignment, FormSettings, FormSubmission, FormTemplate
from fasas.notifications.models import Notification

from .base import FasasTestCase

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def pdf_text(data):
    return " ".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


class ModulisticaTest(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.office = cls.make_user("uff", Role.ADMINISTRATIVE)
        settings_obj = FormSettings.get()
        settings_obj.holder, settings_obj.address = "Cooperativa Prova", "Via Roma 1, Milano"
        settings_obj.contacts, settings_obj.dpo, settings_obj.dpo_contacts = "info@prova.invalid", "Dott. DPO", "dpo@prova.invalid"
        settings_obj.save()

    def template(self, code):
        return FormTemplate.objects.get(code=code)

    def test_predefiniti_e_pdf_vuoto(self):
        self.assertGreaterEqual(FormTemplate.objects.filter(status="published").count(), 9)
        info = self.template("informativa-ospiti")
        text = pdf_text(services.blank_pdf(info))
        self.assertIn("Cooperativa Prova", text)
        self.assertIn("Dott. DPO", text)
        self.assertNotIn("{titolare}", text)
        self.assertIn("Luogo e data", text)  # su carta c'è sempre lo spazio per la firma

    def test_amministratore_modifica_pubblica_e_crea_versioni(self):
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("modulistica:index")).status_code, 200)
        info = self.template("informativa-personale")
        services.submit(info, {"presa_visione": True}, self.operator, subject_user=self.operator)
        url = reverse("modulistica:edit", args=[info.pk])
        page = self.client.get(url)
        self.assertContains(page, "Anteprima online")
        data = {"title": info.title, "intro": info.intro + "\n\nTesto aggiunto.", "for_staff": "on",
                "staff_roles": ["operator"], "document_category": "form", "order": "0",
                "signatures_text": "", "campi-TOTAL_FORMS": "3", "campi-INITIAL_FORMS": "1",
                "campi-MIN_NUM_FORMS": "0", "campi-MAX_NUM_FORMS": "1000"}
        field = info.fields.get()
        data.update({"campi-0-id": field.pk, "campi-0-template": info.pk, "campi-0-order": "0",
                     "campi-0-label": field.label, "campi-0-kind": "check", "campi-0-required": "on",
                     "campi-1-order": "10", "campi-1-label": "Reparto", "campi-1-kind": "choice",
                     "campi-1-options_text": "Primo piano\nSecondo piano", "campi-2-label": ""})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:600])
        info.refresh_from_db()
        self.assertEqual(info.version, 2)  # la versione 1 era già stata compilata
        self.assertEqual(info.fields.count(), 2)
        old = FormSubmission.objects.get(template=info)
        self.assertNotIn("Testo aggiunto", old.snapshot["intro"])  # la compilazione resta com'era
        # nuovo modulo, bozza, poi pubblicato
        response = self.client.post(reverse("modulistica:create"), {
            "title": "Regolamento delle uscite", "intro": "Regole per le uscite.", "for_guests": "on",
            "document_category": "form", "order": "50", "signatures_text": "L'ospite",
            "campi-TOTAL_FORMS": "1", "campi-INITIAL_FORMS": "0", "campi-MIN_NUM_FORMS": "0",
            "campi-MAX_NUM_FORMS": "1000", "campi-0-order": "0", "campi-0-label": "Ho letto il regolamento",
            "campi-0-kind": "check", "campi-0-required": "on"})
        self.assertEqual(response.status_code, 302)
        new = FormTemplate.objects.get(title="Regolamento delle uscite")
        self.assertEqual(new.status, "draft")
        self.client.post(reverse("modulistica:set_status", args=[new.pk, "published"]))
        new.refresh_from_db()
        self.assertTrue(new.is_published)
        # gli altri ruoli non gestiscono la modulistica
        for user in (self.coordinator, self.office, self.operator):
            self.login(user)
            self.assertEqual(self.client.get(reverse("modulistica:index")).status_code, 403)

    def test_distribuzione_e_compilazione_del_personale(self):
        autorizzazione = self.template("autorizzazione-personale")
        # i nuovi utenti ricevono i moduli «anche ai nuovi utenti»
        newcomer = self.make_user("nuovo", Role.OPERATOR)
        self.assertTrue(FormAssignment.objects.filter(user=newcomer, template=autorizzazione).exists())
        self.login(self.admin)
        response = self.client.post(reverse("modulistica:distribute", args=[autorizzazione.pk]),
                                    {"roles": ["operator", "coordinator"]})
        self.assertEqual(response.status_code, 302)
        assignment = FormAssignment.objects.get(user=self.operator, template=autorizzazione)
        self.assertTrue(Notification.objects.filter(recipient=self.operator, kind="form_to_fill").exists())
        self.login(self.operator)
        self.assertContains(self.client.get(reverse("modulistica:mine")), autorizzazione.title)
        page = self.client.get(reverse("modulistica:fill", args=[assignment.pk]))
        self.assertContains(page, "Oper Test")  # {utente} sostituito con il nome
        response = self.client.post(reverse("modulistica:fill", args=[assignment.pk]), {})
        self.assertEqual(response.status_code, 200)  # la dichiarazione è obbligatoria
        response = self.client.post(reverse("modulistica:fill", args=[assignment.pk]), {"accettazione": "on"})
        self.assertRedirects(response, reverse("modulistica:mine"))
        submission = FormSubmission.objects.get(subject_user=self.operator, template=autorizzazione)
        self.assertEqual(submission.status, "confermato online")
        pdf = self.client.get(reverse("modulistica:submission_pdf", args=[submission.pk]))
        self.assertIn("Compilato online", pdf_text(pdf.content))
        # l'amministratore vede chi ha compilato; un collega no
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("modulistica:distribute", args=[autorizzazione.pk])), "Oper Test")
        self.login(self.coordinator)
        self.assertEqual(self.client.get(reverse("modulistica:submission_pdf", args=[submission.pk])).status_code, 403)

    def test_modulo_dell_ospite_da_firmare_e_revoca(self):
        cassa = self.template("cassa-e-oggetti")
        self.login(self.office)
        page = self.client.get(reverse("modulistica:guest", args=[self.guest.pk]))
        self.assertContains(page, cassa.title)
        self.assertNotContains(page, "Anagrafica e sanitario")
        response = self.client.post(reverse("modulistica:guest_fill", args=[self.guest.pk, cassa.pk]), {
            "nome": "Elena Rossi",
            "qualita": "Amministratore di sostegno", "rendiconto": "Mensile", "destinatario": "Elena Rossi",
            "limite_spesa": "30"})
        self.assertRedirects(response, reverse("modulistica:guest", args=[self.guest.pk]))
        submission = FormSubmission.objects.get(template=cassa)
        self.assertEqual(submission.status, "da firmare")
        self.assertEqual(submission.document.category, cassa.document_category)
        self.assertNotIn(submission.document.category, (Document.Category.CONSENT, Document.Category.PAI))
        text = pdf_text(services.read_pdf(submission, self.office))
        self.assertIn("Elena Rossi", text)
        self.assertIn("va comunque firmato", text)
        response = self.client.post(reverse("modulistica:signed_upload", args=[submission.pk]),
                                    {"file": SimpleUploadedFile("firmato.pdf", PDF, "application/pdf")})
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "firmato")
        self.assertEqual(submission.document.versions.count(), 2)
        # consenso alle foto: revocabile
        foto = self.template("foto-lesioni")
        consent = services.submit(foto, {"nome": "Mario Rossi", "qualita": "Ospite", "consenso": "Acconsento"},
                                  self.coordinator, guest=self.guest, respondent="Mario Rossi")
        self.login(self.coordinator)
        self.client.post(reverse("modulistica:withdraw", args=[consent.pk]), {"reason": "Chiesto dall'ospite"})
        consent.refresh_from_db()
        self.assertEqual(consent.status, "revocato")
        with self.assertRaises(services.FormError):
            services.withdraw(submission, self.coordinator, "x")  # l'accordo non è un consenso revocabile
        # l'amministratore di sistema non apre i moduli degli ospiti
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("modulistica:submission_pdf", args=[submission.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("modulistica:guest", args=[self.guest.pk])).status_code, 403)

    def test_familiare_compila_online(self):
        from fasas.core.models import SystemConfig
        from fasas.families.models import FamilyLink

        config = SystemConfig.get()
        config.disabled_modules = []
        config.save()
        family = self.make_user("fam", Role.FAMILY)
        link = FamilyLink.objects.create(user=family, guest=self.guest, relation="family", basis="Consenso")
        info = self.template("informativa-familiari")
        self.login(family)
        self.assertContains(self.client.get(reverse("families:guest", args=[link.pk])), "Informativa per gli utenti")
        response = self.client.post(reverse("modulistica:family_fill", args=[link.pk, info.pk]),
                                    {"nome": "Fam Test", "presa_visione": "on"})
        self.assertRedirects(response, reverse("families:guest", args=[link.pk]))
        submission = FormSubmission.objects.get(family_link=link)
        self.assertEqual(self.client.get(reverse("modulistica:family_pdf", args=[link.pk, submission.pk]))
                         ["Content-Type"], "application/pdf")
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator, kind="form_received").exists())
        # un modulo non destinato ai familiari non si apre
        cassa = self.template("cassa-e-oggetti")
        self.assertEqual(self.client.get(reverse("modulistica:family_fill", args=[link.pk, cassa.pk])).status_code, 404)
