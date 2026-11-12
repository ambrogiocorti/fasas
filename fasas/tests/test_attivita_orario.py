"""Attività a orario per ospite: piano, elenco del turno, spunta con le regole delle registrazioni, ritardi."""
import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from fasas.audit.context import audit_context
from fasas.care import services
from fasas.care.models import CareTask, CareTaskCheck
from fasas.core.shifts import resolve_shift, shift_bounds
from fasas.notifications.models import Notification

from .base import FasasTestCase


def aware(day, hour, minute=0):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)))


class AttivitaOrarioTest(FasasTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        with audit_context(user=self.coordinator):
            self.reposition = CareTask.objects.create(
                guest=self.guest, kind=CareTask.Kind.REPOSITIONING, every_hours=2, first_time=datetime.time(0),
                instructions="Alternare fianco destro, sinistro e supino", start_date=self.today - datetime.timedelta(days=2))
            self.water = CareTask.objects.create(guest=self.guest, kind=CareTask.Kind.HYDRATION,
                                                 times=["10:00", "16:00"], start_date=self.today - datetime.timedelta(days=2))

    def test_orari_dal_piano(self):
        self.assertEqual(len(self.reposition.parsed_times()), 12)
        self.assertEqual(self.water.parsed_times(), [datetime.time(10), datetime.time(16)])
        night = CareTask(guest=self.guest, kind=CareTask.Kind.NIGHT_CHECK, every_hours=2, first_time=datetime.time(0),
                         shifts=["N"])
        self.assertTrue(all(t.hour < 7 or t.hour >= 21 for t in night.parsed_times()))
        self.assertIn("ogni 2 ore", self.reposition.schedule_display())
        with self.assertRaises(ValidationError):
            CareTask(guest=self.guest, kind="other", times=["10:00"], every_hours=2, first_time=datetime.time(8)).clean()
        with self.assertRaises(ValidationError):
            CareTask(guest=self.guest, kind="other").clean()
        with self.assertRaises(ValidationError):
            CareTask(guest=self.guest, kind="other", times=["25:00"]).clean()

    def test_elenco_del_turno_e_spunta(self):
        now = aware(self.today, 10, 5)
        day, shift = resolve_shift(now)
        slots = services.shift_slots(day, shift)
        self.assertTrue(any(s.task == self.water and s.time == datetime.time(10) for s in slots))
        check = services.register_check(self.water, self.operator, self.today, datetime.time(10), now=now,
                                        occurred_at=now)
        self.assertEqual(check.status, CareTaskCheck.Status.DONE)
        self.assertEqual(check.shift, shift)
        slot = next(s for s in services.shift_slots(day, shift) if s.task == self.water and s.time.hour == 10)
        self.assertTrue(slot.done)
        # un collega che spunta la stessa attività: conflitto, nessun doppione
        with self.assertRaises(services.CareError) as error:
            services.register_check(self.water, self.coordinator, self.today, datetime.time(10), now=now)
        self.assertTrue(error.exception.conflict)
        self.assertEqual(CareTaskCheck.objects.filter(task=self.water).count(), 1)

    def test_regole(self):
        now = aware(self.today, 9, 0)
        with self.assertRaisesMessage(services.CareError, "non sono tra gli orari"):
            services.register_check(self.water, self.operator, self.today, datetime.time(11), now=now)
        with self.assertRaisesMessage(services.CareError, "Troppo presto"):
            services.register_check(self.water, self.operator, self.today, datetime.time(16), now=now, occurred_at=now)
        with self.assertRaisesMessage(services.CareError, "motivo"):
            services.register_check(self.water, self.operator, self.today, datetime.time(10), "refused", "",
                                    now=aware(self.today, 10, 0), occurred_at=aware(self.today, 10, 0))
        refused = services.register_check(self.water, self.operator, self.today, datetime.time(10), "refused",
                                          "Non ha sete, riprovare dopo", now=aware(self.today, 10, 0),
                                          occurred_at=aware(self.today, 10, 0))
        self.assertEqual(refused.get_status_display(), "Rifiutata dall'ospite")
        future = self.today + datetime.timedelta(days=1)
        with self.assertRaisesMessage(services.CareError, "futuro"):
            services.register_check(self.water, self.operator, future, datetime.time(10), now=now,
                                    occurred_at=aware(future, 10))

    def test_ospite_archiviato_e_attivita_terminata(self):
        services.end_task(self.water, self.coordinator, "Indicazione del medico")
        with self.assertRaisesMessage(services.CareError, "terminato"):
            services.register_check(self.water, self.operator, self.today, datetime.time(10),
                                    now=aware(self.today, 10), occurred_at=aware(self.today, 10))
        with self.assertRaises(services.CareError):
            services.end_task(self.reposition, self.coordinator, "  ")
        self.guest.status = "archived"
        self.guest.save()
        with self.assertRaisesMessage(services.CareError, "archiviata"):
            services.register_check(self.reposition, self.operator, self.today, datetime.time(10),
                                    now=aware(self.today, 10), occurred_at=aware(self.today, 10))

    def test_turno_chiuso(self):
        from fasas.daily.services import close_shift

        yesterday = self.today - datetime.timedelta(days=1)
        day, shift = resolve_shift(aware(yesterday, 10))
        close_shift(day, shift, user=self.coordinator, handover_notes="")
        with self.assertRaisesMessage(services.CareError, "chiuso"):
            services.register_check(self.water, self.operator, yesterday, datetime.time(10),
                                    now=aware(self.today, 9), occurred_at=aware(yesterday, 10, 5))

    def test_ritardi_e_avviso_al_coordinatore(self):
        now = aware(self.today, 11, 0)  # acqua delle 10:00 non registrata, oltre i 30 minuti
        late = services.late_slots(now)
        self.assertTrue(any(s.task == self.water and s.time.hour == 10 for s in late))
        result = services.late_reminders(now)
        self.assertGreaterEqual(result["late"], 1)
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator, kind="care_late").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.admin, kind="care_late").exists())
        before = Notification.objects.count()
        services.late_reminders(now)  # una sola volta per orario
        self.assertEqual(Notification.objects.count(), before)

    def test_pagine_e_permessi(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("care:due")).status_code, 200)
        page = self.client.get(reverse("care:guest", args=[self.guest.pk]))
        self.assertContains(page, "Riposizionamento")
        self.assertEqual(self.client.get(reverse("care:create", args=[self.guest.pk])).status_code, 403)
        day, shift = resolve_shift()
        slots = [s for s in services.shift_slots(day, shift) if not s.done]
        slot = min(slots, key=lambda s: abs((s.moment - timezone.now()).total_seconds()))
        with mock.patch("fasas.care.services.EARLY_TOLERANCE", datetime.timedelta(hours=24)):
            response = self.client.post(reverse("care:check_quick"), {
                "task": slot.task.pk, "day": slot.day.isoformat(), "time": slot.time.strftime("%H:%M")})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CareTaskCheck.objects.filter(task=slot.task, scheduled_time=slot.time).exists())
        # il coordinatore crea un piano dalla pagina
        self.login(self.coordinator)
        response = self.client.post(reverse("care:create", args=[self.guest.pk]), {
            "kind": "night_check", "times_text": "23:00, 03:00", "late_minutes": "30",
            "start_date": self.today.isoformat()})
        self.assertEqual(response.status_code, 302, response.content.decode()[:500])
        night = CareTask.objects.get(kind="night_check")
        self.assertEqual(night.times, ["03:00", "23:00"])
        # l'amministratore di sistema non vede i dati di assistenza
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("care:due")).status_code, 403)

    def test_cruscotto_operatore_e_menu(self):
        self.login(self.operator)
        page = self.client.get(reverse("core:dashboard"))
        self.assertContains(page, "Attività a orario")
        self.assertContains(page, reverse("care:due"))
        self.assertGreater(len(shift_bounds(*resolve_shift())), 1)
