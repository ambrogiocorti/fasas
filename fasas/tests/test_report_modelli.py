"""Report configurabili (report di analisi, P1): sezioni, colonne, ordine, PDF ed Excel, ogni N giorni."""
import datetime
from io import BytesIO

from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from pypdf import PdfReader

from fasas.clinical.models import ClinicalEvent
from fasas.core.encryption import read_encrypted
from fasas.reports.models import GeneratedReport, ReportSchedule, ReportTemplate
from fasas.reports.services import generate_from_template, run_due_schedules

from .base import FasasTestCase


class ReportTemplateTests(FasasTestCase):
    def setUp(self):
        self.event = ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="Caduta in bagno")
        self.day = self.event.shift_date

    def test_template_form_saves_sections_in_order_with_columns(self):
        self.login(self.coordinator)
        response = self.client.post(reverse("reports:template_create"), {
            "name": "Vigilanza ATS", "description": "",
            "include_events": "on", "order_events": "1", "columns_events": ["Data/ora", "Ospite"],
            "include_medications": "on", "order_medications": "2", "columns_medications": ["Data/ora", "Farmaco"],
        })
        self.assertEqual(response.status_code, 302, response.content[:500])
        template = ReportTemplate.objects.get()
        self.assertEqual([s["type"] for s in template.sections], ["events", "medications"])
        self.assertEqual(template.sections[0]["columns"], ["Data/ora", "Ospite"])
        self.assertContains(self.client.get(reverse("reports:template_list")), "Vigilanza ATS")

    def test_template_needs_at_least_one_section_and_column(self):
        self.login(self.coordinator)
        response = self.client.post(reverse("reports:template_create"), {"name": "Vuoto"})
        self.assertContains(response, "almeno una sezione")
        response = self.client.post(reverse("reports:template_create"), {"name": "Senza colonne",
                                                                         "include_events": "on"})
        self.assertContains(response, "almeno una colonna")

    def test_both_formats_with_only_chosen_columns(self):
        template = ReportTemplate.objects.create(name="Eventi essenziali", sections=[
            {"type": "events", "columns": ["Data/ora", "Ospite"]},
            {"type": "medications", "columns": ["Farmaco"]},
        ])
        pdf, xlsx = generate_from_template(template, "both", self.day, self.day, user=self.coordinator)
        self.assertEqual({pdf.format, xlsx.format}, {"pdf", "xlsx"})
        text = PdfReader(BytesIO(read_encrypted(pdf.storage_name))).pages[0].extract_text()
        self.assertIn("Eventi sanitari", text)
        self.assertIn("Farmaci somministrati", text)
        workbook = load_workbook(BytesIO(read_encrypted(xlsx.storage_name)))
        self.assertEqual(len(workbook.sheetnames), 2)
        headers = [c.value for c in workbook.worksheets[0][4]]
        self.assertEqual(headers, ["Data/ora", "Ospite"])

    def test_manual_generation_from_the_page(self):
        template = ReportTemplate.objects.create(name="Solo eventi", sections=[{"type": "events", "columns": ["Ospite"]}])
        self.login(self.coordinator)
        self.client.post(reverse("reports:list"), {"template": template.pk, "format": "both",
                                                   "start": self.day.isoformat(), "end": self.day.isoformat()})
        self.assertEqual(GeneratedReport.objects.filter(report_type="custom").count(), 2)


class IntervalScheduleTests(FasasTestCase):
    def test_every_n_days(self):
        template = ReportTemplate.objects.create(name="Ogni 10 giorni", sections=[{"type": "events", "columns": []}])
        schedule = ReportSchedule.objects.create(name="Decadale", template=template, format="both",
                                                 frequency="interval", interval_days=10)
        today = timezone.localdate()
        self.assertEqual(run_due_schedules(today)["generated"], 1)
        reports = GeneratedReport.objects.filter(schedule=schedule)
        self.assertEqual(reports.count(), 2)  # PDF ed Excel
        first = reports.first()
        self.assertEqual((first.period_start, first.period_end),
                         (today - datetime.timedelta(days=10), today - datetime.timedelta(days=1)))
        for offset in range(1, 10):
            self.assertEqual(run_due_schedules(today + datetime.timedelta(days=offset))["generated"], 0, offset)
        self.assertEqual(run_due_schedules(today + datetime.timedelta(days=10))["generated"], 1)

    def test_schedule_form_requires_content_and_interval(self):
        self.login(self.coordinator)
        response = self.client.post(reverse("reports:schedule_create"), {
            "name": "Senza contenuto", "format": "pdf", "frequency": "interval", "retention_years": "5"})
        self.assertContains(response, "Scegliere il contenuto")
        self.assertContains(response, "ogni quanti giorni")
