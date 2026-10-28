import datetime

from django.utils import timezone

from fasas.appointments.models import Appointment
from fasas.appointments.services import send_reminders
from fasas.clinical.models import ClinicalEvent
from fasas.notifications.models import Notification
from fasas.pai.models import PAI

from .base import FasasTestCase


class PAITests(FasasTestCase):
    def test_full_pai_lifecycle(self):
        self.login(self.coordinator)
        self.client.post(f"/pai/ospite/{self.guest.pk}/nuovo/")
        pai = PAI.objects.get(guest=self.guest)
        self.assertEqual(pai.status, "draft")
        response = self.client.post(f"/pai/{pai.pk}/approva/")
        self.assertEqual(response.status_code, 302)
        pai.refresh_from_db()
        self.assertEqual(pai.status, "draft")  # senza obiettivi non si approva
        self.client.post(f"/pai/{pai.pk}/obiettivo/", {
            "area": "autonomy", "objective": "Vestirsi in autonomia", "intervention": "Affiancamento",
            "responsible": self.operator.pk, "verification_date": (timezone.localdate() + datetime.timedelta(days=30)).isoformat(),
            "order": 0})
        self.assertEqual(pai.goals.count(), 1)
        self.client.post(f"/pai/{pai.pk}/approva/")
        pai.refresh_from_db()
        self.assertEqual(pai.status, "active")
        self.assertIsNotNone(pai.document)  # PDF archiviato tra i documenti
        self.assertTrue(pai.document.current_version.is_pdf)
        # una volta in vigore non è più modificabile: si crea una revisione
        self.assertEqual(self.client.get(f"/pai/{pai.pk}/modifica/").status_code, 403)
        self.client.post(f"/pai/{pai.pk}/revisione/")
        revision = PAI.objects.get(guest=self.guest, version=2)
        self.assertEqual(revision.goals.count(), 1)
        self.client.post(f"/pai/{revision.pk}/approva/")
        pai.refresh_from_db()
        self.assertEqual(pai.status, "superseded")

    def test_operator_cannot_approve(self):
        pai = PAI.objects.create(guest=self.guest, version=1, review_due=timezone.localdate())
        self.login(self.operator)
        self.client.post(f"/pai/{pai.pk}/approva/")
        pai.refresh_from_db()
        self.assertEqual(pai.status, "draft")


class AppointmentTests(FasasTestCase):
    def test_reminders_tomorrow_and_today_once(self):
        now = timezone.localtime()
        tomorrow = Appointment.objects.create(guest=self.guest, title="Neurologo",
                                              scheduled_at=now + datetime.timedelta(days=1), companion=self.operator)
        send_reminders()
        send_reminders()
        notes = Notification.objects.filter(kind="appointment_tomorrow", recipient=self.operator)
        self.assertEqual(notes.count(), 1)
        tomorrow.refresh_from_db()
        self.assertTrue(tomorrow.reminded_day_before)
        send_reminders(now=now + datetime.timedelta(days=1))
        self.assertTrue(Notification.objects.filter(kind="appointment_today", recipient=self.operator).exists())


class SearchTests(FasasTestCase):
    def test_global_search(self):
        ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="Scivolato in giardino")
        self.make_therapy()
        self.login(self.coordinator)
        response = self.client.get("/cerca/", {"q": "giardino"})
        self.assertContains(response, "Eventi sanitari")
        response = self.client.get("/cerca/", {"q": "paracetamolo"})
        self.assertContains(response, "Tachipirina")
        response = self.client.get("/cerca/", {"q": "Rossi"})
        self.assertContains(response, "Rossi Mario")
        response = self.client.get("/cerca/", {"guest": self.guest.pk, "type": "events",
                                                "date_from": timezone.localdate().isoformat()})
        self.assertContains(response, "Scivolato")
