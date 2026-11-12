"""Casi critici richiesti dal collaudo che non avevano ancora un test dedicato."""
import datetime
import uuid

from django.urls import reverse
from django.utils import timezone

from fasas.clinical.models import Therapy, TherapyAdministration
from fasas.core.shifts import resolve_shift
from fasas.notifications.models import Notification
from fasas.offline.models import OfflineRecord

from .base import FasasTestCase


class TerapiaSenzaPermessiTest(FasasTestCase):
    def setUp(self):
        self.therapy = self.make_therapy(schedule_times=["08:00", "20:00"])

    def test_operatore_non_modifica_ne_sospende_una_terapia(self):
        self.login(self.operator)
        update = self.client.post(reverse("clinical:therapy_update", args=[self.therapy.pk]),
                                  {"dose": "10", "schedule_times": "08:00"})
        self.assertEqual(update.status_code, 403)
        status = self.client.post(reverse("clinical:therapy_status", args=[self.therapy.pk]),
                                  {"status": "suspended", "status_reason": "prova"})
        self.assertEqual(status.status_code, 403)
        self.therapy.refresh_from_db()
        self.assertEqual(self.therapy.status, Therapy.Status.ACTIVE)
        self.assertEqual(self.therapy.parsed_times(), [datetime.time(8), datetime.time(20)])

    def test_amministrativo_non_vede_le_terapie(self):
        from fasas.accounts.models import Role

        administrative = self.make_user("ammin", Role.ADMINISTRATIVE)
        self.login(administrative)
        self.assertIn(self.client.get(reverse("clinical:therapy_detail", args=[self.therapy.pk])).status_code, (403, 404))
        self.assertIn(self.client.get(reverse("clinical:guest_therapies", args=[self.guest.pk])).status_code, (403, 404))


class SenzaReteCasiCriticiTest(FasasTestCase):
    def setUp(self):
        self.therapy = self.make_therapy(schedule_times=["00:00", "08:00", "14:30", "20:00"])

    def record(self):
        when = timezone.now() - datetime.timedelta(minutes=5)
        day, _ = resolve_shift(when)
        slot = min(self.therapy.parsed_times(), key=lambda t: abs(
            (datetime.datetime.combine(day, t) - timezone.localtime(when).replace(tzinfo=None)).total_seconds()))
        return {"uuid": str(uuid.uuid4()), "kind": "administration", "occurred_at": when.isoformat(),
                "guest": self.guest.pk, "therapy": self.therapy.pk, "day": day.isoformat(),
                "time": slot.strftime("%H:%M"), "status": "given"}

    def test_terapia_sospesa_mentre_il_telefono_era_senza_rete(self):
        """La dose non diventa valida da sola, ma non si perde: resta da verificare e il coordinatore è avvisato."""
        data = self.record()
        self.therapy.status = Therapy.Status.SUSPENDED
        self.therapy.status_reason = "Sospesa dal medico"
        self.therapy.save()
        self.login(self.operator)
        response = self.client.post(reverse("offline:sync"), {"user": self.operator.username, "records": [data]},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["status"], "rejected")
        self.assertIn("sospesa", result["message"])
        self.assertFalse(TherapyAdministration.objects.filter(therapy=self.therapy).exists())
        record = OfflineRecord.objects.get(uuid=data["uuid"])
        self.assertEqual(record.status, OfflineRecord.Status.REJECTED)
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator, kind="offline_sync").exists())

    def test_operatore_disattivato_non_sincronizza(self):
        data = self.record()
        self.login(self.operator)
        self.operator.is_active = False
        self.operator.save()
        response = self.client.post(reverse("offline:sync"), {"user": self.operator.username, "records": [data]},
                                    content_type="application/json")
        self.assertIn(response.status_code, (302, 401, 403))
        self.assertFalse(TherapyAdministration.objects.exists())
        self.assertFalse(OfflineRecord.objects.filter(uuid=data["uuid"]).exists())

    def test_invio_ripetuto_dopo_un_riavvio_non_duplica(self):
        data = self.record()
        self.login(self.operator)
        for _ in range(3):
            response = self.client.post(reverse("offline:sync"), {"user": self.operator.username, "records": [data]},
                                        content_type="application/json")
            self.assertEqual(response.json()["results"][0]["status"], "ok")
        self.assertEqual(TherapyAdministration.objects.filter(therapy=self.therapy).count(), 1)
        self.assertEqual(OfflineRecord.objects.filter(uuid=data["uuid"]).count(), 1)
