import datetime

from django.utils import timezone

from fasas.clinical.models import ClinicalEvent
from fasas.core.locking import edit_decision
from fasas.core.models import SystemConfig
from fasas.daily.services import close_shift
from fasas.guests.services import discharge_and_archive

from .base import FasasTestCase


class EditLockTests(FasasTestCase):
    def make_event(self, age_hours):
        event = ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="x",
                                             occurred_at=timezone.now() - datetime.timedelta(hours=age_hours))
        ClinicalEvent.objects.filter(pk=event.pk).update(created_at=timezone.now() - datetime.timedelta(hours=age_hours))
        event.refresh_from_db()
        return event

    def set_policy(self, policy):
        config = SystemConfig.get()
        config.edit_lock_policy = policy
        config.save()

    def test_within_window_is_free(self):
        decision = edit_decision(self.make_event(2), self.operator)
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.reason_required)

    def test_after_window_with_reason(self):
        self.set_policy(SystemConfig.EditLockPolicy.AFTER_WINDOW_REASON)
        decision = edit_decision(self.make_event(30), self.operator)
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.reason_required)

    def test_after_window_locked(self):
        self.set_policy(SystemConfig.EditLockPolicy.WITHIN_WINDOW)
        self.assertFalse(edit_decision(self.make_event(30), self.coordinator).allowed)

    def test_after_window_only_coordinator(self):
        self.set_policy(SystemConfig.EditLockPolicy.AFTER_WINDOW_COORDINATOR)
        event = self.make_event(30)
        self.assertFalse(edit_decision(event, self.operator).allowed)
        decision = edit_decision(event, self.coordinator)
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.reason_required)

    def test_closed_shift_locks_everything(self):
        event = self.make_event(1)
        close_shift(event.shift_date, event.shift, self.operator)
        self.assertFalse(edit_decision(event, self.coordinator).allowed)
        self.assertFalse(edit_decision(event, self.admin).allowed)

    def test_archived_guest_is_read_only(self):
        event = self.make_event(1)
        discharge_and_archive(self.guest, self.coordinator, timezone.localdate(), "Trasferimento")
        event.refresh_from_db()
        self.assertFalse(edit_decision(event, self.coordinator).allowed)
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.is_archived)
        self.assertIsNotNone(self.guest.retention_until)

    def test_view_requires_reason_after_window(self):
        self.set_policy(SystemConfig.EditLockPolicy.AFTER_WINDOW_REASON)
        event = self.make_event(30)
        self.login(self.operator)
        url = f"/sanitario/evento/{event.pk}/modifica/"
        response = self.client.get(url)
        self.assertContains(response, "Motivazione della modifica")
        data = {"event_type": "fall", "severity": "low", "occurred_at": timezone.localtime(event.occurred_at).strftime("%Y-%m-%dT%H:%M"),
                "description": "Descrizione corretta"}
        self.assertEqual(self.client.post(url, data).status_code, 200)  # manca la motivazione
        response = self.client.post(url, {**data, "edit_reason": "Errore di battitura"})
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.description, "Descrizione corretta")
        from fasas.audit.models import AuditLog

        self.assertTrue(AuditLog.objects.filter(object_id=str(event.pk), reason="Errore di battitura").exists())
