import datetime

from django.utils import timezone

from fasas.core.models import SystemConfig
from fasas.core.shifts import Shift, resolve_shift, shift_bounds
from fasas.daily.models import ChecklistItem, DailyRecord, EvacuationRecord, ShiftClosure
from fasas.daily.services import auto_close_shifts, checklist_status, days_since_last_evacuation, mark_check

from .base import FasasTestCase


class ShiftTests(FasasTestCase):
    def test_resolve_shift(self):
        tz = timezone.get_current_timezone()
        day = datetime.date(2026, 3, 10)
        at = lambda h, m=0: timezone.make_aware(datetime.datetime.combine(day, datetime.time(h, m)), tz)  # noqa: E731
        self.assertEqual(resolve_shift(at(7)), (day, Shift.MORNING))
        self.assertEqual(resolve_shift(at(13, 59)), (day, Shift.MORNING))
        self.assertEqual(resolve_shift(at(14)), (day, Shift.AFTERNOON))
        self.assertEqual(resolve_shift(at(22)), (day, Shift.NIGHT))
        self.assertEqual(resolve_shift(at(3)), (day - datetime.timedelta(days=1), Shift.NIGHT))
        start, end = shift_bounds(day, Shift.NIGHT)
        self.assertEqual(end - start, datetime.timedelta(hours=10))

    def test_auto_close_past_shifts(self):
        result = auto_close_shifts()
        self.assertGreater(result["closed"], 0)
        day, shift = resolve_shift()
        self.assertFalse(ShiftClosure.objects.filter(date=day, shift=shift).exists())  # il turno in corso resta aperto
        self.assertTrue(ShiftClosure.objects.filter(automatic=True).exists())
        self.assertEqual(auto_close_shifts()["closed"], 0)


class EvacuationTests(FasasTestCase):
    def test_days_since_last_evacuation(self):
        days, last = days_since_last_evacuation(self.guest)
        self.assertEqual(days, 10)  # dall'ingresso
        self.assertIsNone(last)
        EvacuationRecord.objects.create(guest=self.guest, outcome=False)
        EvacuationRecord.objects.create(guest=self.guest, outcome=True,
                                        occurred_at=timezone.now() - datetime.timedelta(days=2))
        days, last = days_since_last_evacuation(self.guest)
        self.assertEqual(days, 2)

    def test_mode_b_accepts_verified_negative_records(self):
        """Report di analisi, P1: in modalità B il «non avvenuta» verificato si distingue dal dato mancante."""
        config = SystemConfig.get()
        config.evacuation_mode = SystemConfig.EvacuationMode.ON_EVENT
        config.save()
        self.login(self.operator)
        self.client.post(f"/giornaliero/evacuazioni/{self.guest.pk}/rapida/", {"outcome": "0"})
        self.assertTrue(EvacuationRecord.objects.filter(outcome=False).exists())
        self.client.post(f"/giornaliero/evacuazioni/{self.guest.pk}/rapida/", {"outcome": "1"})
        self.assertTrue(EvacuationRecord.objects.filter(outcome=True).exists())

    def test_days_without_evacuation_are_explained(self):
        from fasas.daily.services import evacuation_documentation
        from fasas.guests.models import AdmissionEvent

        today = timezone.localdate()
        EvacuationRecord.objects.create(guest=self.guest, outcome=True,
                                        occurred_at=timezone.now() - datetime.timedelta(days=6))
        EvacuationRecord.objects.create(guest=self.guest, outcome=False,
                                        occurred_at=timezone.now() - datetime.timedelta(days=5))
        AdmissionEvent.objects.create(guest=self.guest, kind="hospitalization", date=today - datetime.timedelta(days=3))
        AdmissionEvent.objects.create(guest=self.guest, kind="return", date=today - datetime.timedelta(days=1))
        days, last, counts = evacuation_documentation(self.guest)
        self.assertEqual(days, 6)
        # giornate concluse da 5 giorni fa a ieri: 1 «non avvenuta», 2 di ricovero, 2 senza registrazioni
        self.assertEqual(counts, {"not_occurred": 1, "missing": 2, "absent": 2})
        self.login(self.coordinator)
        page = self.client.get("/giornaliero/evacuazioni/")
        self.assertContains(page, "2 non documentati")
        self.assertContains(page, "2 di assenza")

    def test_protocol_message_separates_missing_data(self):
        from fasas.protocols.engine import check_evacuation
        from fasas.protocols.models import Protocol

        Protocol.objects.filter(kind="evacuation").update(params={"days": 3})
        EvacuationRecord.objects.create(guest=self.guest, outcome=True,
                                        occurred_at=timezone.now() - datetime.timedelta(days=4))
        activations = check_evacuation(self.guest)
        self.assertTrue(activations)
        self.assertIn("non documentati", activations[0].trigger_summary)
        self.assertEqual(activations[0].trigger_data["missing"], 3)


class ChecklistTests(FasasTestCase):
    def test_checklist_auto_and_manual_items(self):
        day, _ = resolve_shift()
        shift = Shift.MORNING
        morning_start, _ = shift_bounds(day, shift)
        status = checklist_status(day, shift)
        self.assertGreater(status["total"], 0)
        self.assertEqual(status["done"], 0)
        DailyRecord.objects.create(guest=self.guest, category="meal", meal="breakfast",
                                   occurred_at=morning_start + datetime.timedelta(hours=1))
        status = checklist_status(day, shift)
        breakfast = next(r for r in status["rows"] if r["item"].meal == "breakfast")
        self.assertEqual(breakfast["cells"][0]["state"], "ok")
        therapy_row = next(r for r in status["rows"] if r["item"].check_type == "therapy")
        self.assertEqual(therapy_row["cells"][0]["state"], "na")  # nessun farmaco programmato
        hygiene = ChecklistItem.objects.get(template__shift=shift, check_type="hygiene")
        mark_check(day, shift, hygiene, self.operator, self.guest, not_applicable=True)
        status = checklist_status(day, shift)
        row = next(r for r in status["rows"] if r["item"] == hygiene)
        self.assertEqual(row["cells"][0]["state"], "na")

    def test_close_shift_view_records_missing(self):
        day, shift = resolve_shift()
        self.login(self.operator)
        response = self.client.post(f"/giornaliero/chiusure/chiudi/?date={day}&shift={shift}",
                                    {"confirm": "on", "handover_notes": "Tutto tranquillo"})
        self.assertEqual(response.status_code, 302)
        closure = ShiftClosure.objects.get(date=day, shift=shift)
        self.assertTrue(closure.summary["missing"])
        self.assertEqual(closure.handover_notes, "Tutto tranquillo")
