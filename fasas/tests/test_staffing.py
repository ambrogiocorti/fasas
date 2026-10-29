import datetime
import json

from django.urls import reverse
from django.utils import timezone

from fasas.accounts.models import Role
from fasas.billing.services import month_days, month_start, shift_month
from fasas.notifications.models import Notification
from fasas.staffing import services
from fasas.staffing.models import RotaEntry, RotaSettings, ShiftChange

from .base import FasasTestCase


class StaffingTests(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.oper2 = cls.make_user("oper2", Role.OPERATOR)
        cls.oper3 = cls.make_user("oper3", Role.OPERATOR)

    def setUp(self):
        self.next_month = shift_month(month_start(), 1)
        self.day = lambda n: self.next_month.replace(day=n)

    def put(self, user, day, code):
        services.set_entry(user, day, code, notify=False)

    def test_staff_excludes_doctors_and_admins(self):
        names = {u.username for u, _ in services.staff()}
        self.assertEqual(names, {"coord", "oper", "oper2", "oper3"})

    def test_coverage_and_rest_warnings(self):
        rules = RotaSettings.get()
        rules.min_morning, rules.min_afternoon, rules.min_night = 2, 1, 1
        rules.max_consecutive_days = 3
        rules.save()
        self.put(self.operator, self.day(1), "P")
        self.put(self.operator, self.day(2), "M")    # pomeriggio → mattina: 10 ore di riposo
        self.put(self.oper2, self.day(1), "N")
        self.put(self.oper2, self.day(2), "P")       # notte → pomeriggio: 7 ore di riposo
        for n in range(3, 8):
            self.put(self.oper3, self.day(n), "M")   # 5 giorni consecutivi > 3
        grid = services.month_grid(self.next_month)
        texts = " | ".join(w["text"] for w in grid["warnings"])
        self.assertIn("pomeriggio seguito da mattina – riposo di 10 ore", texts)
        self.assertIn("notte seguito da pomeriggio – riposo di 7 ore", texts)
        self.assertIn("più di 3 giorni di lavoro consecutivi", texts)
        day1 = {code: cells[0] for code, cells in grid["coverage"].items()}
        self.assertEqual((day1["M"]["count"], day1["M"]["ok"]), (0, False))
        self.assertTrue(day1["P"]["ok"] and day1["N"]["ok"])
        row = next(r for r in grid["rows"] if r["user"] == self.operator)
        self.assertEqual(row["hours"], services.shift_hours("P", self.day(1)) + services.shift_hours("M", self.day(2)))

    def test_painter_save_publish_and_change_notifications(self):
        self.login(self.coordinator)
        changes = [{"user": self.operator.pk, "day": self.day(d).isoformat(), "code": "M"} for d in (3, 4)]
        changes.append({"user": self.oper2.pk, "day": self.day(3).isoformat(), "code": "N", "lead": True})
        mese = f"{self.next_month:%Y-%m}"
        self.client.post(reverse("staffing:save"), {"mese": mese, "changes": json.dumps(changes)})
        self.assertEqual(RotaEntry.objects.count(), 3)
        self.assertTrue(RotaEntry.objects.get(user=self.oper2).is_lead)
        self.assertFalse(Notification.objects.filter(kind="rota_changed").exists())  # non ancora pubblicato
        self.client.post(reverse("staffing:publish"), {"mese": mese})
        published = Notification.objects.filter(kind="rota_published")
        self.assertEqual(set(published.values_list("recipient__username", flat=True)), {"coord", "oper", "oper2", "oper3"})
        self.client.post(reverse("staffing:save"), {"mese": mese, "changes": json.dumps(
            [{"user": self.operator.pk, "day": self.day(4).isoformat(), "code": "P"}])})
        changed = Notification.objects.get(kind="rota_changed")
        self.assertEqual(changed.recipient, self.operator)
        self.assertIn("da mattina a pomeriggio", changed.message)
        # Un operatore non può modificare il calendario
        self.login(self.operator)
        self.assertEqual(self.client.post(reverse("staffing:save"), {"changes": "[]"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("staffing:rota")).status_code, 200)

    def test_repeat_cycle(self):
        previous = month_start()
        for offset, day in enumerate(month_days(previous)[-28:]):
            self.put(self.operator, day, ["M", "P", "N", "R"][offset % 4])
        self.put(self.operator, month_days(previous)[-27], "F")  # le ferie non si ripetono
        created = services.repeat_cycle(self.next_month)
        self.assertGreaterEqual(created, 20)
        self.assertFalse(RotaEntry.objects.filter(date__gte=self.next_month, code="F").exists())

    def test_leave_request_flow(self):
        for n in range(10, 13):
            self.put(self.operator, self.day(n), "M")
            self.put(self.oper2, self.day(n), "M")
        leave = services.request_leave(self.operator, "F", self.day(10), self.day(12), "Matrimonio")
        self.assertTrue(Notification.objects.filter(kind="rota_request", recipient=self.coordinator).exists())
        self.assertFalse(Notification.objects.filter(kind="rota_request", recipient=self.oper2).exists())
        impact = services.coverage_impact(self.operator, services._days(leave.start, leave.end), "F")
        self.assertEqual(len(impact), 3)  # la mattina scende a 1 su 2
        with self.assertRaises(services.RotaError):
            services.request_leave(self.operator, "F", self.day(11), self.day(15))
        self.login(self.coordinator)
        page = self.client.get(reverse("staffing:requests"))
        self.assertContains(page, "resterebbero 1 su 2")
        self.client.post(reverse("staffing:decide_leave", args=[leave.pk]), {"approve": "1", "note": "Auguri"})
        self.assertEqual(set(RotaEntry.objects.filter(user=self.operator, date__gte=self.day(10), date__lte=self.day(12))
                             .values_list("code", flat=True)), {"F"})
        self.assertTrue(Notification.objects.filter(kind="rota_answer", recipient=self.operator).exists())

    def test_swap_and_cover(self):
        day = timezone.localdate() + datetime.timedelta(days=3)
        self.put(self.operator, day, "M")
        self.put(self.oper2, day, "P")
        swap = services.propose_change(self.operator, ShiftChange.Kind.SWAP, day, self.oper2, "Visita medica")
        with self.assertRaises(services.RotaError):
            services.decide_change(swap, self.coordinator, True)  # il collega non ha ancora accettato
        services.respond_change(swap, self.oper2, True)
        services.decide_change(swap, self.coordinator, True)
        self.assertEqual(RotaEntry.objects.get(user=self.operator, date=day).code, "P")
        self.assertEqual(RotaEntry.objects.get(user=self.oper2, date=day).code, "M")
        # Sostituzione: oper3 è libero e copre il turno di oper
        cover = services.propose_change(self.operator, ShiftChange.Kind.COVER, day, self.oper3)
        services.respond_change(cover, self.oper3, True)
        services.decide_change(cover, self.coordinator, True)
        self.assertEqual(RotaEntry.objects.get(user=self.oper3, date=day).code, "P")
        self.assertEqual(RotaEntry.objects.get(user=self.operator, date=day).code, "R")
        with self.assertRaises(services.RotaError):
            services.propose_change(self.operator, ShiftChange.Kind.SWAP, day, self.oper2)  # oper è a riposo

    def test_upcoming_only_published(self):
        today = timezone.localdate()
        self.put(self.operator, today + datetime.timedelta(days=1), "N")
        self.assertEqual(services.upcoming(self.operator), [])
        services.publish(month_start(today + datetime.timedelta(days=1)), self.coordinator)
        if month_start(today) != month_start(today + datetime.timedelta(days=1)):
            services.publish(month_start(today), self.coordinator)
        self.assertEqual([e.code for e in services.upcoming(self.operator)], ["N"])
        self.login(self.operator)
        self.assertContains(self.client.get(reverse("core:dashboard")), "I miei prossimi turni")
        self.assertContains(self.client.get(reverse("staffing:my")), "Chiedi ferie o permesso")
