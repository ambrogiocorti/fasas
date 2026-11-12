"""
Controlli unici sulle somministrazioni (report di analisi, P0): stessi esiti da pagina web, API e lavoro senza rete.
Casi positivi, negativi e registrazioni contemporanee.
"""
import datetime
import uuid
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from fasas.clinical.models import Therapy, TherapyAdministration
from fasas.clinical.services import AdministrationError, register_administration
from fasas.core.models import SystemConfig
from fasas.core.shifts import resolve_shift
from fasas.daily.services import close_shift
from fasas.notifications.models import Notification

from .base import FasasTestCase


class ScheduledDoseTests(FasasTestCase):
    def setUp(self):
        self.therapy = self.make_therapy(schedule_times=["08:00", "20:00"])
        self.yesterday = timezone.localdate() - datetime.timedelta(days=1)

    def register(self, **kwargs):
        data = {"scheduled_date": self.yesterday, "scheduled_time": datetime.time(8, 0)}
        data.update(kwargs)
        return register_administration(self.therapy, self.operator, **data)

    def assertRefused(self, text, **kwargs):
        with self.assertRaisesMessage(AdministrationError, text):
            self.register(**kwargs)
        self.assertFalse(TherapyAdministration.objects.exists())

    def test_valid_dose_is_registered(self):
        adm = self.register()
        self.assertEqual(adm.scheduled_time, datetime.time(8, 0))

    def test_time_not_prescribed(self):
        self.assertRefused("non sono tra gli orari prescritti", scheduled_time=datetime.time(9, 0))

    def test_future_day(self):
        self.assertRefused("giorno futuro", scheduled_date=timezone.localdate() + datetime.timedelta(days=1))

    def test_before_start_and_frequency(self):
        self.assertRefused("non prevede dosi", scheduled_date=self.therapy.start_date - datetime.timedelta(days=1))
        Therapy.objects.filter(pk=self.therapy.pk).update(every_n_days=2)
        self.therapy.refresh_from_db()
        odd_day = self.therapy.start_date + datetime.timedelta(days=1)
        self.assertRefused("non prevede dosi", scheduled_date=odd_day)

    def test_suspended_therapy(self):
        Therapy.objects.filter(pk=self.therapy.pk).update(status=Therapy.Status.SUSPENDED)
        self.therapy.refresh_from_db()
        self.assertRefused("sospesa")

    def test_missing_slot_and_future_time(self):
        self.assertRefused("Indicare la dose programmata", scheduled_date=None, scheduled_time=None)
        self.assertRefused("nel futuro", occurred_at=timezone.now() + datetime.timedelta(hours=1))

    def test_archived_guest(self):
        self.guest.status = "archived"
        self.guest.archived_at = timezone.now()
        self.guest.save()
        self.therapy.refresh_from_db()
        self.assertRefused("archiviata")

    def test_closed_shift_of_the_dose(self):
        day, shift = resolve_shift(timezone.make_aware(datetime.datetime.combine(self.yesterday, datetime.time(8, 0))))
        close_shift(day, shift, user=self.coordinator, handover_notes="")
        self.assertRefused("chiuso")

    def test_duplicate_is_a_conflict(self):
        self.register()
        with self.assertRaises(AdministrationError) as ctx:
            self.register()
        self.assertTrue(ctx.exception.conflict)
        self.assertEqual(TherapyAdministration.objects.count(), 1)

    def test_simultaneous_registrations_leave_one_dose(self):
        """Due operatori nello stesso istante: il controllo passa a entrambi, il database ne accetta uno solo."""
        self.register()
        with mock.patch("fasas.clinical.services.check_administration", return_value=[]):
            with self.assertRaises(AdministrationError) as ctx:
                self.register()
        self.assertTrue(ctx.exception.conflict)
        self.assertEqual(TherapyAdministration.objects.count(), 1)

    def test_voided_dose_can_be_registered_again(self):
        adm = self.register()
        adm.void(self.coordinator, "registrata sull'ospite sbagliato")
        self.register()
        self.assertEqual(TherapyAdministration.objects.count(), 1)


class SameRulesOnEveryChannelTests(FasasTestCase):
    def setUp(self):
        self.therapy = self.make_therapy(schedule_times=["08:00"])
        self.day = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()

    def test_web_board(self):
        self.login(self.operator)
        url = reverse("clinical:administer", args=[self.therapy.pk])
        response = self.client.post(url, {"day": self.day, "time": "09:00", "status": "given"}, follow=True)
        self.assertContains(response, "non sono tra gli orari prescritti")
        self.client.post(url, {"day": self.day, "time": "08:00", "status": "given"})
        response = self.client.post(url, {"day": self.day, "time": "08:00", "status": "given"}, follow=True)
        self.assertContains(response, "Dose già registrata")
        self.assertEqual(TherapyAdministration.objects.count(), 1)

    def test_web_board_ignores_external_return_address(self):
        self.login(self.operator)
        response = self.client.post(reverse("clinical:administer", args=[self.therapy.pk]),
                                    {"day": self.day, "time": "08:00", "status": "given",
                                     "next": "https://sito-esterno.example/"})
        self.assertEqual(response["Location"], reverse("clinical:board"))

    @override_settings(FASAS_API_ENABLED=True)
    def test_api(self):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.operator).key}")
        bad = api.post("/api/v1/somministrazioni/", {"therapy": self.therapy.pk, "scheduled_date": self.day,
                                                     "scheduled_time": "09:00", "status": "given"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("orari prescritti", bad.json()["detail"])
        ok = api.post("/api/v1/somministrazioni/", {"therapy": self.therapy.pk, "scheduled_date": self.day,
                                                    "scheduled_time": "08:00", "status": "given"})
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_offline(self):
        self.login(self.operator)
        record = {"uuid": str(uuid.uuid4()), "kind": "administration", "guest": self.guest.pk,
                  "occurred_at": timezone.now().isoformat(), "therapy": self.therapy.pk, "day": self.day,
                  "time": "09:00", "status": "given"}
        results = self.client.post(reverse("offline:sync"), {"user": "oper", "records": [record]},
                                   content_type="application/json").json()["results"]
        self.assertEqual(results[0]["status"], "rejected")
        self.assertIn("orari prescritti", results[0]["message"])


class SosLimitTests(FasasTestCase):
    def setUp(self):
        self.sos = self.make_therapy(is_sos=True, schedule_times=[], sos_indication="Febbre", sos_max_daily=1)
        register_administration(self.sos, self.operator, sos_reason="TC 38.2",
                                occurred_at=timezone.now() - datetime.timedelta(hours=2))

    def test_reason_is_required(self):
        with self.assertRaisesMessage(AdministrationError, "motivo"):
            register_administration(self.sos, self.operator, sos_reason=" ")

    def test_warn_policy_needs_confirmation_and_reason(self):
        with self.assertRaises(AdministrationError) as ctx:
            register_administration(self.sos, self.operator, sos_reason="TC 38.9")
        self.assertTrue(ctx.exception.limits)
        with self.assertRaises(AdministrationError):
            register_administration(self.sos, self.operator, sos_reason="TC 38.9", confirm_limits=True)
        adm = register_administration(self.sos, self.operator, sos_reason="TC 38.9", confirm_limits=True,
                                      limit_reason="indicazione telefonica del medico reperibile")
        self.assertTrue(adm.sos_limit_override)
        self.assertIn("medico reperibile", adm.sos_limit_note)
        self.assertTrue(Notification.objects.filter(title__contains="oltre i limiti", recipient=self.doctor).exists())

    def test_block_policy(self):
        SystemConfig.objects.update(sos_limit_policy=SystemConfig.SosLimitPolicy.BLOCK)
        with self.assertRaisesMessage(AdministrationError, "blocca"):
            register_administration(self.sos, self.operator, sos_reason="TC 39", confirm_limits=True,
                                    limit_reason="insiste")
        adm = register_administration(self.sos, self.doctor, sos_reason="TC 39", confirm_limits=True,
                                      limit_reason="valutato il paziente")
        self.assertTrue(adm.sos_limit_override)

    def test_web_form_asks_for_the_reason(self):
        self.login(self.operator)
        url = reverse("clinical:sos_administer", args=[self.guest.pk])
        data = {"therapy": self.sos.pk, "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "sos_reason": "TC 39.1"}
        self.assertContains(self.client.post(url, data), "Per procedere confermare e scrivere il motivo")
        data.update(confirm_limits="on", limit_reason="medico reperibile avvisato")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(TherapyAdministration.objects.filter(sos_limit_override=True).count(), 1)

    def _offline_sos(self):
        self.login(self.operator)
        record = {"uuid": str(uuid.uuid4()), "kind": "sos", "guest": self.guest.pk,
                  "occurred_at": timezone.now().isoformat(), "therapy": self.sos.pk, "reason": "crisi"}
        return self.client.post(reverse("offline:sync"), {"user": "oper", "records": [record]},
                                content_type="application/json").json()["results"][0]

    def test_offline_warn_policy_registers_and_flags(self):
        result = self._offline_sos()
        self.assertIn(result["status"], ("ok", "warning"))
        self.assertTrue(TherapyAdministration.objects.filter(sos_limit_override=True).exists())

    def test_offline_block_policy_leaves_it_to_the_coordinator(self):
        SystemConfig.objects.update(sos_limit_policy=SystemConfig.SosLimitPolicy.BLOCK)
        result = self._offline_sos()
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(TherapyAdministration.objects.count(), 1)
