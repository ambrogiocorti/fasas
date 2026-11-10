"""Area familiari e tutori: spenta di default, perimetro del familiare, messaggi, visite, documenti, cassa."""
import datetime

from django.urls import reverse
from django.utils import timezone

from fasas.accounts.models import Role
from fasas.audit.models import AuditLog
from fasas.core import modules
from fasas.core.models import SystemConfig
from fasas.documents.models import Document
from fasas.documents.services import create_document
from fasas.families import services
from fasas.families.models import FamilyLink, FamilyMessage, VisitRequest
from fasas.notifications.models import Notification

from .base import FasasTestCase
from .test_documents import sample_pdf


def switch_on():
    config = SystemConfig.get()
    config.disabled_modules = [k for k in config.disabled_modules if k != "families"]
    config.save()


class AreaFamiliariTest(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.daughter = cls.make_user("figlia", Role.FAMILY)
        cls.stranger = cls.make_user("estraneo", Role.FAMILY)
        cls.other_guest = cls.make_guest("BNCLRA45A41F205Y", first_name="Lara", last_name="Bianchi")

    def setUp(self):
        switch_on()
        self.link = FamilyLink.objects.create(user=self.daughter, guest=self.guest, relation="family",
                                              description="figlia", basis="Consenso dell'ospite del 02/11/2026",
                                              can_see_documents=True)
        FamilyLink.objects.create(user=self.stranger, guest=self.other_guest, relation="family", basis="Consenso")

    def test_spenta_di_default(self):
        config = SystemConfig.get()
        config.disabled_modules = list(modules.DEFAULT_OFF)
        config.save()
        self.assertFalse(modules.is_on("families"))
        self.login(self.daughter)
        self.assertEqual(self.client.get(reverse("families:home")).status_code, 404)  # «funzione spenta»
        self.login(self.coordinator)
        self.assertNotContains(self.client.get(reverse("core:dashboard")), reverse("families:staff_home"))

    def test_il_familiare_vede_solo_il_suo_perimetro(self):
        self.login(self.daughter)
        self.assertRedirects(self.client.get(reverse("core:dashboard")), reverse("families:home"),
                             target_status_code=302)
        page = self.client.get(reverse("families:guest", args=[self.link.pk]))
        self.assertContains(page, "Messaggi con la struttura")
        self.assertNotContains(page, "Anagrafica e sanitario")
        other = FamilyLink.objects.get(user=self.stranger)
        self.assertEqual(self.client.get(reverse("families:guest", args=[other.pk])).status_code, 403)
        # nessuna pagina del personale, nemmeno quelle senza permessi specifici
        for url in (reverse("guests:detail", args=[self.guest.pk]), reverse("search:search"),
                    reverse("staffing:my_credentials"), reverse("families:staff_home")):
            response = self.client.get(url)
            self.assertIn(response.status_code, (302, 403), url)
            if response.status_code == 302:
                self.assertEqual(response.url, reverse("families:home"))
        self.assertEqual(self.client.get(reverse("notifications:list")).status_code, 200)

    def test_messaggi_e_notifiche(self):
        self.login(self.daughter)
        self.client.post(reverse("families:guest", args=[self.link.pk]), {"body": "Come ha passato la notte?"})
        message = FamilyMessage.objects.get()
        self.assertTrue(message.from_family)
        notice = Notification.objects.get(recipient=self.coordinator, kind="family_message")
        self.assertNotIn("notte", notice.message)  # il testo non finisce nelle notifiche
        self.assertFalse(Notification.objects.filter(recipient=self.operator, kind="family_message").exists())
        self.login(self.coordinator)
        self.client.post(reverse("families:staff_link", args=[self.link.pk]), {"body": "Ha dormito bene."})
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)
        self.assertTrue(Notification.objects.filter(recipient=self.daughter, kind="family_update").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.stranger).exists())

    def test_visite(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.login(self.daughter)
        self.client.post(reverse("families:guest", args=[self.link.pk]),
                         {"day": tomorrow.isoformat(), "time": "16:00", "people": "2", "notes": ""})
        visit = VisitRequest.objects.get()
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator, kind="family_visit").exists())
        with self.assertRaisesMessage(services.FamilyError, "futuri"):
            services.request_visit(self.link, self.daughter, timezone.localdate() - datetime.timedelta(days=1),
                                   datetime.time(10))
        self.login(self.coordinator)
        with self.assertRaisesMessage(services.FamilyError, "motivo"):
            services.decide_visit(visit, self.coordinator, False, "")
        self.client.post(reverse("families:visit_decide", args=[visit.pk]), {"confirm": "1", "note": "Vi aspettiamo"})
        visit.refresh_from_db()
        self.assertEqual(visit.status, VisitRequest.Status.CONFIRMED)
        self.login(self.daughter)
        self.client.post(reverse("families:visit_cancel", args=[self.link.pk, visit.pk]))
        visit.refresh_from_db()
        self.assertEqual(visit.status, VisitRequest.Status.CANCELLED)

    def test_documenti_condivisi_uno_per_uno(self):
        document = create_document(self.guest, Document.Category.OTHER, "Menù della settimana", user=self.coordinator,
                                   data=sample_pdf(), filename="menu.pdf")
        private = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione clinica",
                                  user=self.coordinator, data=sample_pdf(), filename="relazione.pdf")
        self.login(self.coordinator)
        self.client.post(reverse("families:staff_guest", args=[self.guest.pk]), {"document": document.pk})
        share = document.family_shares.get()
        self.login(self.daughter)
        page = self.client.get(reverse("families:guest", args=[self.link.pk]))
        self.assertContains(page, "Menù della settimana")
        self.assertNotContains(page, "Relazione clinica")
        response = self.client.get(reverse("families:document", args=[self.link.pk, share.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(AuditLog.objects.filter(action="download", user=self.daughter).exists())
        # senza «vede i documenti» non si apre nulla
        self.link.can_see_documents = False
        self.link.save()
        response = self.client.get(reverse("families:document", args=[self.link.pk, share.pk]))
        self.assertRedirects(response, reverse("families:guest", args=[self.link.pk]))
        self.assertFalse(private.family_shares.exists())

    def test_cassa_per_il_tutore_e_revoca(self):
        from fasas.personal.services import add_movement

        add_movement(self.guest, self.coordinator, "deposit", "50", "Versamento del tutore")
        self.login(self.daughter)
        self.assertNotContains(self.client.get(reverse("families:guest", args=[self.link.pk])), "Cassa personale")
        self.link.can_see_cash = True
        self.link.save()
        self.assertContains(self.client.get(reverse("families:guest", args=[self.link.pk])), "50,00")
        pdf = self.client.get(reverse("families:cash", args=[self.link.pk]), {"mese": timezone.localdate().strftime("%Y-%m")})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        services.revoke_link(self.link, self.coordinator, "Fine della tutela")
        self.assertEqual(self.client.get(reverse("families:guest", args=[self.link.pk])).status_code, 403)

    def test_collegamento_dal_coordinatore(self):
        self.login(self.coordinator)
        response = self.client.post(reverse("families:link_create"), {
            "user": self.stranger.pk, "guest": self.guest.pk, "relation": "guardian", "description": "tutore",
            "basis": "Decreto di nomina n. 123/2026", "active": "on"})
        self.assertEqual(response.status_code, 302, response.content.decode()[:300])
        self.assertTrue(FamilyLink.objects.filter(user=self.stranger, guest=self.guest, relation="guardian").exists())
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("families:staff_home")).status_code, 403)
