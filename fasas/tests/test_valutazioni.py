"""
Scale di valutazione: punteggi e fasce, rivalutazione, promemoria, collegamento al PAI e alla cartella.
"""
import datetime

from django.urls import reverse
from django.utils import timezone

from fasas.assessments.models import Assessment, ScaleSetting
from fasas.assessments.scales import SCALES
from fasas.assessments.services import (
    AssessmentError,
    create_assessment,
    due_list,
    due_reminders,
    score,
    settings_by_code,
)
from fasas.core.jobs import run_job
from fasas.notifications.models import Notification

from .base import FasasTestCase


def answers_for(scale, pick=max):
    return {item.key: pick(points for points, _ in item.options) for item in scale.items}


class ScaleDefinitionTests(FasasTestCase):
    def test_bands_cover_every_possible_total(self):
        for scale in SCALES.values():
            for total in range(scale.min_total, scale.max_total + 1):
                self.assertIsNotNone(scale.band_for(total), f"{scale.code}: nessuna fascia per {total}")

    def test_known_totals(self):
        self.assertEqual(SCALES["barthel"].max_total, 100)
        self.assertEqual((SCALES["braden"].min_total, SCALES["braden"].max_total), (6, 23))
        self.assertEqual((SCALES["norton"].min_total, SCALES["norton"].max_total), (5, 20))
        self.assertEqual(SCALES["tinetti"].max_total, 28)
        self.assertEqual(SCALES["painad"].max_total, 10)

    def test_score_and_band(self):
        braden = SCALES["braden"]
        _clean, total, band = score(braden, answers_for(braden, min))
        self.assertEqual((total, band.level), (6, "danger"))
        _clean, total, band = score(braden, answers_for(braden, max))
        self.assertEqual((total, band.label), (23, "nessun rischio rilevato"))

    def test_missing_or_invalid_item_is_refused(self):
        braden = SCALES["braden"]
        answers = answers_for(braden)
        answers.pop("nutrition")
        with self.assertRaisesMessage(AssessmentError, "Nutrizione"):
            score(braden, answers)
        answers = answers_for(braden)
        answers["nutrition"] = 9
        with self.assertRaisesMessage(AssessmentError, "Punteggio non previsto"):
            score(braden, answers)


class CreateAssessmentTests(FasasTestCase):
    def test_creation_sets_next_due_from_settings(self):
        assessment = create_assessment(self.guest, "braden", answers_for(SCALES["braden"]), self.operator)
        self.assertEqual(assessment.total, 23)
        self.assertEqual(assessment.next_due, timezone.localdate() + datetime.timedelta(days=30))
        setting = ScaleSetting.objects.get(code="braden")
        setting.interval_days = 0
        setting.save()
        again = create_assessment(self.guest, "braden", answers_for(SCALES["braden"]), self.operator)
        self.assertIsNone(again.next_due)

    def test_disabled_scale_unknown_scale_future_date(self):
        settings_by_code()
        self.assertFalse(ScaleSetting.objects.get(code="norton").enabled)  # spenta per default
        with self.assertRaisesMessage(AssessmentError, "non è in uso"):
            create_assessment(self.guest, "norton", answers_for(SCALES["norton"]), self.operator)
        with self.assertRaisesMessage(AssessmentError, "non prevista"):
            create_assessment(self.guest, "mmse", {}, self.operator)
        with self.assertRaisesMessage(AssessmentError, "nel futuro"):
            create_assessment(self.guest, "painad", answers_for(SCALES["painad"]), self.operator,
                              occurred_at=timezone.now() + datetime.timedelta(hours=2))
        self.assertFalse(Assessment.objects.exists())

    def test_archived_guest_is_refused(self):
        self.guest.status = "archived"
        self.guest.archived_at = timezone.now()
        self.guest.save()
        with self.assertRaises(AssessmentError):
            create_assessment(self.guest, "painad", answers_for(SCALES["painad"]), self.operator)

    def test_settings_are_created_once(self):
        settings_by_code()
        settings_by_code()
        self.assertEqual(ScaleSetting.objects.count(), len(SCALES))


class DueTests(FasasTestCase):
    def test_never_done_then_done_then_expired(self):
        today = timezone.localdate()
        codes = {row["scale"].code for row in due_list(today)}
        self.assertEqual(codes, {"barthel", "braden", "tinetti"})  # le scale «al bisogno» non scadono
        create_assessment(self.guest, "braden", answers_for(SCALES["braden"]), self.operator)
        self.assertNotIn("braden", {row["scale"].code for row in due_list(today)})
        in_25_days = today + datetime.timedelta(days=25)
        row = next(r for r in due_list(in_25_days) if r["scale"].code == "braden")
        self.assertFalse(row["overdue"])  # in scadenza entro 7 giorni
        row = next(r for r in due_list(today + datetime.timedelta(days=31)) if r["scale"].code == "braden")
        self.assertTrue(row["overdue"])

    def test_reminders_once_per_due_date(self):
        result = due_reminders()
        self.assertEqual(result["overdue"], 3)
        due_reminders()
        notes = Notification.objects.filter(kind="assessment_due", recipient=self.coordinator)
        self.assertEqual(notes.count(), 3)
        self.assertFalse(Notification.objects.filter(kind="assessment_due", recipient=self.operator).exists())

    def test_job_is_registered(self):
        self.assertIn("overdue", run_job("assessments"))

    def test_archived_guests_are_not_listed(self):
        self.guest.status = "archived"
        self.guest.archived_at = timezone.now()
        self.guest.save()
        self.assertEqual(due_list(), [])


class AssessmentViewTests(FasasTestCase):
    def post_braden(self, user, **extra):
        self.login(user)
        data = {f"item_{key}": value for key, value in answers_for(SCALES["braden"], min).items()}
        data.update({"occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "notes": "prima valutazione"})
        data.update(extra)
        return self.client.post(reverse("assessments:create", args=[self.guest.pk, "braden"]), data)

    def test_operator_records_and_sees_band(self):
        response = self.post_braden(self.operator)
        assessment = Assessment.objects.get()
        self.assertRedirects(response, assessment.get_absolute_url())
        self.assertEqual((assessment.total, assessment.band), (6, "rischio molto alto"))
        page = self.client.get(assessment.get_absolute_url())
        self.assertContains(page, "rischio molto alto")
        self.assertContains(page, "Percezione sensoriale")
        guest_page = self.client.get(reverse("assessments:guest", args=[self.guest.pk]))
        self.assertContains(guest_page, "Scala di Braden")
        self.assertContains(guest_page, "Indice di Barthel")

    def test_incomplete_form_is_not_saved(self):
        response = self.post_braden(self.operator, item_mobility="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Assessment.objects.exists())

    def test_unknown_scale_redirects(self):
        self.login(self.operator)
        response = self.client.get(reverse("assessments:create", args=[self.guest.pk, "mmse"]))
        self.assertRedirects(response, reverse("assessments:guest", args=[self.guest.pk]))

    def test_disabled_scale_shows_error(self):
        settings_by_code()
        self.login(self.operator)
        data = {f"item_{key}": value for key, value in answers_for(SCALES["norton"]).items()}
        data["occurred_at"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("assessments:create", args=[self.guest.pk, "norton"]), data)
        self.assertContains(response, "non è in uso")

    def test_void_keeps_history(self):
        self.post_braden(self.operator)
        assessment = Assessment.objects.get()
        self.login(self.coordinator)
        response = self.client.post(reverse("assessments:void", args=[assessment.pk]), {"reason": "scala sbagliata"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Assessment.objects.exists())
        self.assertTrue(Assessment.all_objects.get(pk=assessment.pk).is_voided)
        self.assertContains(self.client.get(reverse("assessments:guest", args=[self.guest.pk])), "annullat")

    def test_due_page_and_settings(self):
        self.login(self.coordinator)
        self.assertContains(self.client.get(reverse("assessments:due")), "Indice di Barthel")
        data = {}
        for code, scale in SCALES.items():
            if code != "tinetti":
                data[f"enabled_{code}"] = "on"
            data[f"interval_{code}"] = 90 if code == "barthel" else scale.interval_days
        response = self.client.post(reverse("assessments:settings"), data)
        self.assertRedirects(response, reverse("assessments:settings"))
        configured = settings_by_code()
        self.assertEqual(configured["barthel"].interval_days, 90)
        self.assertFalse(configured["tinetti"].enabled)
        self.assertTrue(configured["norton"].enabled)
        bad = self.client.post(reverse("assessments:settings"), {"interval_barthel": "molti"})
        self.assertRedirects(bad, reverse("assessments:settings"))
        self.assertEqual(settings_by_code()["barthel"].interval_days, 90)

    def test_permissions(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("assessments:settings")).status_code, 403)
        self.post_braden(self.operator)
        assessment = Assessment.objects.get()
        self.assertEqual(self.client.post(reverse("assessments:void", args=[assessment.pk]),
                                          {"reason": "x"}).status_code, 403)
        self.client.logout()
        response = self.client.get(reverse("assessments:guest", args=[self.guest.pk]))
        self.assertEqual(response.status_code, 302)  # al login

    def test_pai_and_guest_folder_show_latest_assessment(self):
        from fasas.pai.models import PAI
        from fasas.reports.guest_export import build_guest_folder

        self.post_braden(self.operator)
        pai = PAI.objects.create(guest=self.guest, version=1,
                                 review_due=timezone.localdate() + datetime.timedelta(days=180))
        self.login(self.coordinator)
        page = self.client.get(reverse("pai:detail", args=[pai.pk]))
        self.assertContains(page, "Valutazioni più recenti")
        self.assertContains(page, "rischio molto alto")
        pdf = build_guest_folder(self.guest, self.coordinator)
        self.assertTrue(pdf.startswith(b"%PDF"))
