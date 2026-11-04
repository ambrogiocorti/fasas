"""«Segnala un problema» e indicatori del pilota."""
import datetime

from django.urls import reverse
from django.utils import timezone

from fasas.audit.context import audit_context
from fasas.clinical.models import TherapyAdministration
from fasas.core.shifts import Shift
from fasas.daily.services import close_shift
from fasas.feedback.metrics import pilot_metrics
from fasas.feedback.models import Feedback
from fasas.notifications.models import Notification

from .base import FasasTestCase


class FeedbackTests(FasasTestCase):
    def test_operator_reports_problem_page_without_query(self):
        self.login(self.operator)
        url = reverse("feedback:create") + "?da=/ospiti/1/%3Fq%3DRossi"
        self.assertContains(self.client.get(url), "Niente nomi né dati sanitari")
        response = self.client.post(url, {"kind": "hard", "text": "Il pulsante salva è troppo in basso"})
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.page, "/ospiti/1/")
        self.assertEqual(feedback.created_by, self.operator)
        self.assertRedirects(response, "/ospiti/1/", fetch_redirect_response=False)
        self.assertTrue(Notification.objects.filter(recipient=self.admin, kind="feedback").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.operator, kind="feedback").exists())

    def test_external_page_ignored(self):
        self.login(self.operator)
        self.client.post(reverse("feedback:create") + "?da=https://esempio.it/x", {"kind": "idea", "text": "Idea"})
        self.assertEqual(Feedback.objects.get().page, "")

    def test_top_bar_button(self):
        self.login(self.operator)
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("feedback:create"))

    def test_permissions(self):
        feedback = Feedback.objects.create(created_by=self.operator, kind="error", text="Errore 500 al salvataggio")
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("feedback:list")).status_code, 403)
        self.login(self.coordinator)
        self.assertContains(self.client.get(reverse("feedback:list")), "Errore 500 al salvataggio")
        self.assertEqual(self.client.post(reverse("feedback:handle", args=[feedback.pk]),
                                          {"status": "done", "reply": "x"}).status_code, 403)
        self.login(self.admin)
        self.client.post(reverse("feedback:handle", args=[feedback.pk]), {"status": "done", "reply": "Corretto"})
        feedback.refresh_from_db()
        self.assertEqual((feedback.status, feedback.reply, feedback.handled_by), ("done", "Corretto", self.admin))
        csv = self.client.get(reverse("feedback:list") + "?stato=tutte&formato=csv").content.decode()
        self.assertIn("Errore 500 al salvataggio", csv)


class PilotMetricsTests(FasasTestCase):
    def test_doses_rounds_and_checklist(self):
        day = timezone.localdate() - datetime.timedelta(days=1)
        tz = timezone.get_current_timezone()
        at = lambda h, m: timezone.make_aware(datetime.datetime.combine(day, datetime.time(h, m)), tz)  # noqa: E731
        guests = [self.guest, self.make_guest("BNCLRA80A41F205Y", first_name="Laura", last_name="Bianchi"),
                  self.make_guest("VRDGPP80A01F205Z", first_name="Giuseppe", last_name="Verdi")]
        drug = self.make_drug()
        therapies = [self.make_therapy(drug=drug, guest=g, schedule_times=["08:00"],
                                       start_date=day - datetime.timedelta(days=3)) for g in guests]
        with audit_context(user=self.operator):
            for therapy, (occurred, created) in zip(therapies[:2], [(at(8, 10), at(8, 10)), (at(9, 30), at(8, 35))], strict=True):
                adm = TherapyAdministration.objects.create(
                    guest=therapy.guest, therapy=therapy, scheduled_date=day, scheduled_time=datetime.time(8),
                    occurred_at=occurred, created_by=self.operator)
                TherapyAdministration.objects.filter(pk=adm.pk).update(created_at=created)
            closure = close_shift(day, Shift.MORNING, user=self.coordinator)
        self.assertEqual((closure.summary["doses_total"], closure.summary["doses_documented"],
                          closure.summary["doses_missing"], closure.summary["doses_late"]), (3, 2, 1, 1))

        data = pilot_metrics(day, day)
        totals = data["totals"]
        self.assertEqual((totals["doses_total"], totals["doses_missing"], totals["doses_late"]), (3, 1, 1))
        self.assertEqual(totals["documented_pct"], 67)
        self.assertEqual(totals["round_median"], 25)
        self.assertEqual(data["slots"][0]["time"], datetime.time(8))

        self.login(self.coordinator)
        page = self.client.get(reverse("feedback:metrics") + f"?dal={day}&al={day}")
        self.assertContains(page, "25 min")
        csv = self.client.get(reverse("feedback:metrics") + f"?dal={day}&al={day}&formato=csv").content.decode()
        self.assertIn(f"{day:%d/%m/%Y};1;3;2;1;1;25", csv)

    def test_operator_cannot_see_metrics(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("feedback:metrics")).status_code, 403)


class InspectionPackageTests(FasasTestCase):
    def test_coordinator_generates_and_archives_pdf(self):
        from fasas.reports.models import GeneratedReport

        self.make_therapy()
        self.login(self.coordinator)
        url = reverse("reports:inspection")
        self.assertContains(self.client.get(url), "vigilanza ATS/ASL")
        today = timezone.localdate()
        response = self.client.post(url, {"start": today - datetime.timedelta(days=29), "end": today})
        report = GeneratedReport.objects.get(report_type="inspection")
        self.assertRedirects(response, reverse("reports:download", args=[report.pk]), fetch_redirect_response=False)
        pdf = self.client.get(reverse("reports:download", args=[report.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_sections_follow_modules(self):
        from pypdf import PdfReader

        from fasas.core.models import SystemConfig
        from fasas.reports.inspection import build_inspection

        def text():
            today = timezone.localdate()
            reader = PdfReader(__import__("io").BytesIO(build_inspection(today - datetime.timedelta(days=7), today)))
            return " ".join(page.extract_text() for page in reader.pages)

        content = text()
        self.assertIn("Ospiti in carico (1)", content)
        self.assertIn("SENZA PAI", content)
        self.assertIn("Protocolli automatici in vigore", content)
        config = SystemConfig.get()
        config.disabled_modules = ["pai", "protocols"]
        config.save()
        content = text()
        self.assertNotIn("SENZA PAI", content)
        self.assertNotIn("Protocolli automatici in vigore", content)

    def test_operator_cannot_generate(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("reports:inspection")).status_code, 403)
