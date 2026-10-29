import datetime
import json
import uuid
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.clinical.models import ClinicalEvent, ParameterReading, ParameterType, TherapyAdministration
from fasas.core.shifts import resolve_shift
from fasas.daily.models import DiaryEntry
from fasas.daily.services import close_shift
from fasas.notifications.models import Notification, PushSubscription
from fasas.notifications.services import notify
from fasas.offline.models import OfflineRecord

from .base import FasasTestCase

SUBSCRIPTION = {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": "BPk3", "auth": "c2Vj"}}


@override_settings(FASAS_PUSH_ASYNC=False, FASAS_PUSH_SHOW_DETAILS=False,
                   FASAS_VAPID_PRIVATE_KEY="DXaXXWyDn06T_HXQBV8K1mBtgv_NjykfwKXuHDcDCak")
class PushTests(FasasTestCase):
    def subscribe(self, user, endpoint=SUBSCRIPTION["endpoint"]):
        self.login(user)
        response = self.client.post(reverse("notifications:push_subscribe"), {**SUBSCRIPTION, "endpoint": endpoint},
                                    content_type="application/json", HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14) Chrome/130")
        self.assertEqual(response.status_code, 200)
        return PushSubscription.objects.get(endpoint=endpoint)

    def test_subscription_and_device_page(self):
        sub = self.subscribe(self.operator)
        self.assertEqual(sub.user, self.operator)
        self.assertEqual(sub.label, "Chrome su Android")
        page = self.client.get(reverse("notifications:devices"))
        self.assertContains(page, "Chrome su Android")
        self.assertContains(page, 'data-public-key="B')
        # Lo stesso browser usato poi da un altro utente passa al nuovo utente
        self.subscribe(self.coordinator)
        self.assertEqual(PushSubscription.objects.get().user, self.coordinator)
        bad = self.client.post(reverse("notifications:push_subscribe"), {"endpoint": "http://x", "keys": {}},
                               content_type="application/json")
        self.assertEqual(bad.status_code, 400)

    def test_push_payload_has_no_health_data(self):
        self.subscribe(self.coordinator)
        with mock.patch("fasas.notifications.push.webpush") as webpush, self.captureOnCommitCallbacks(execute=True):
            notify("sos_validation", f"SOS da validare: {self.guest}", "Diazepam 5 mg", guest=self.guest)
        self.assertEqual(webpush.call_count, 1)
        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual(payload["title"], "FASAS · Farmaco SOS da validare")
        self.assertNotIn("Rossi", json.dumps(payload))
        notification = Notification.objects.get(recipient=self.coordinator)
        self.assertEqual(payload["url"], reverse("notifications:open", args=[notification.pk]))
        self.assertEqual(webpush.call_args.kwargs["headers"]["Urgency"], "normal")

    def test_kinds_without_push_and_expired_subscriptions(self):
        from pywebpush import WebPushException

        sub = self.subscribe(self.coordinator)
        with mock.patch("fasas.notifications.push.webpush") as webpush, self.captureOnCommitCallbacks(execute=True):
            notify("stock_low", "Farmaco in esaurimento")
        webpush.assert_not_called()
        gone = WebPushException("gone", response=mock.Mock(status_code=410))
        with mock.patch("fasas.notifications.push.webpush", side_effect=gone), self.captureOnCommitCallbacks(execute=True):
            notify("protocol_activated", "Protocollo")
        self.assertFalse(PushSubscription.objects.filter(pk=sub.pk).exists())

    def test_open_marks_read_and_follows_link(self):
        notify("protocol_activated", "Protocollo", link="/protocolli/")
        notification = Notification.objects.filter(recipient=self.operator).get()
        self.login(self.operator)
        response = self.client.get(reverse("notifications:open", args=[notification.pk]))
        self.assertRedirects(response, "/protocolli/", fetch_redirect_response=False)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_service_worker_and_manifest_are_public(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("javascript", response["Content-Type"])
        self.assertIn("showNotification", response.content.decode())
        manifest = self.client.get("/manifest.webmanifest")
        self.assertEqual(json.loads(manifest.content)["display"], "standalone")


class OfflineTests(FasasTestCase):
    def setUp(self):
        self.drug = self.make_drug()
        self.therapy = self.make_therapy(drug=self.drug, schedule_times=["08:00", "14:30", "20:00"])
        self.sos = self.make_therapy(drug=self.make_drug("Diazepam", "diazepam", "N05BA01"), is_sos=True,
                                     schedule_times=[], sos_indication="crisi > 3 minuti", sos_max_daily=2)
        self.guest.allergies.create(substance="penicillina", severity="severe")

    def record(self, kind, minutes_ago=5, **data):
        when = timezone.now() - datetime.timedelta(minutes=minutes_ago)
        return {"uuid": str(uuid.uuid4()), "kind": kind, "occurred_at": when.isoformat(), "guest": self.guest.pk, **data}

    def sync(self, user, records):
        self.login(user)
        response = self.client.post(reverse("offline:sync"), {"user": user.username, "records": records},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def test_pack_contents_and_access(self):
        self.assertEqual(self.client.get(reverse("offline:pack")).status_code, 401)
        for user in (self.doctor, self.admin):
            self.login(user)
            self.assertEqual(self.client.get(reverse("offline:pack")).status_code, 403, user.username)
        self.login(self.operator)
        response = self.client.get(reverse("offline:pack"))
        self.assertIn("no-store", response["Cache-Control"])
        pack = response.json()
        self.assertEqual(pack["user"]["username"], "oper")
        self.assertEqual(len(pack["shifts"]), 2)
        guest = next(g for g in pack["guests"] if g["id"] == self.guest.pk)
        self.assertEqual(guest["allergies"][0]["substance"], "penicillina")
        self.assertTrue(any(s["therapy"] == self.sos.pk and s["max_daily"] == 2 for s in pack["sos"]))
        self.assertTrue(all(d["therapy"] == self.therapy.pk for d in pack["doses"]))
        self.assertTrue(pack["permissions"]["administration"])

    def test_offline_page_is_an_empty_shell(self):
        response = self.client.get(reverse("offline:page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-offline-app")
        self.assertNotContains(response, self.guest.last_name)
        self.assertEqual(self.client.get(reverse("offline:status")).status_code, 401)

    def test_administration_sync_is_idempotent_and_keeps_real_time(self):
        day, _ = resolve_shift(timezone.now() - datetime.timedelta(minutes=5))
        data = self.record("administration", therapy=self.therapy.pk, day=day.isoformat(), time="08:00", status="given")
        first = self.sync(self.operator, [data])
        self.assertEqual(first[0]["status"], "ok")
        again = self.sync(self.operator, [data])
        self.assertEqual(again[0]["status"], "ok")
        adm = TherapyAdministration.objects.get(therapy=self.therapy)
        self.assertEqual(adm.created_by, self.operator)
        self.assertEqual(adm.occurred_at.isoformat()[:16], datetime.datetime.fromisoformat(data["occurred_at"]).isoformat()[:16])
        self.assertTrue(AuditLog.objects.filter(source="offline", object_id=str(adm.pk)).exists())
        # Stessa dose registrata da un altro dispositivo: conflitto, nessun duplicato
        other = self.record("administration", therapy=self.therapy.pk, day=day.isoformat(), time="08:00", status="given")
        conflict = self.sync(self.coordinator, [other])
        self.assertEqual(conflict[0]["status"], "conflict")
        self.assertIn("già registrata", conflict[0]["message"])
        self.assertEqual(TherapyAdministration.objects.filter(therapy=self.therapy).count(), 1)

    def test_closed_shift_is_accepted_as_late_and_notified(self):
        when = timezone.now() - datetime.timedelta(minutes=5)
        day, shift = resolve_shift(when)
        close_shift(day, shift, user=self.coordinator, handover_notes="")
        results = self.sync(self.operator, [self.record("diary", text="Tranquillo, riposa.")])
        self.assertEqual(results[0]["status"], "late")
        self.assertTrue(DiaryEntry.objects.filter(guest=self.guest, text="Tranquillo, riposa.").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator, kind="offline_sync").exists())

    def test_sos_parameter_event_and_rejections(self):
        temp = ParameterType.objects.get(code="temperature") if ParameterType.objects.filter(code="temperature").exists() \
            else ParameterType.objects.create(code="temperature", name="Temperatura", unit="°C")
        results = self.sync(self.operator, [
            self.record("sos", therapy=self.sos.pk, reason="Crisi tonico-clonica di 4 minuti", dose="5 mg"),
            self.record("parameter", parameter_type=temp.pk, value="38,4"),
            self.record("event", event_type="seizure", severity="medium", description="Crisi di 4 minuti", duration_minutes="4"),
            self.record("sos", therapy=self.sos.pk, reason=""),
            self.record("diary", minutes_ago=-60, text="nel futuro"),
            self.record("unknown"),
        ])
        self.assertEqual([r["status"] for r in results], ["ok", "ok", "ok", "rejected", "rejected", "rejected"])
        sos = TherapyAdministration.objects.get(therapy=self.sos)
        self.assertEqual(sos.validation_status, "pending")
        self.assertEqual(ParameterReading.objects.get(guest=self.guest, parameter_type=temp).value, Decimal("38.4"))
        self.assertEqual(ClinicalEvent.objects.get(guest=self.guest).duration_minutes, 4)
        self.assertEqual(OfflineRecord.objects.count(), 6)

    def test_permissions_and_user_mismatch(self):
        self.login(self.doctor)
        response = self.client.post(reverse("offline:sync"), {"records": []}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.login(self.operator)
        response = self.client.post(reverse("offline:sync"), {"user": "altro", "records": []},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_emergency_sheet_pdf(self):
        self.login(self.operator)
        response = self.client.get(reverse("offline:emergency"))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertTrue(AuditLog.objects.filter(action="export", reason__icontains="emergenza").exists())

    def test_records_page_scope(self):
        self.sync(self.operator, [self.record("diary", text="Nota offline")])
        self.sync(self.coordinator, [self.record("diary", text="Nota del coordinatore")])
        self.login(self.operator)
        page = self.client.get(reverse("offline:records"))
        self.assertContains(page, "(le mie)")
        self.assertEqual(len(page.context["records"]), 1)
        self.login(self.coordinator)
        self.assertEqual(len(self.client.get(reverse("offline:records")).context["records"]), 2)
        self.login(self.doctor)
        self.assertEqual(self.client.get(reverse("offline:records")).status_code, 403)
