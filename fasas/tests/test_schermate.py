"""
Schermate di uso quotidiano: ospiti, registro, evacuazioni, diario, checklist, chiusura turni, terapie, parametri,
eventi, contenzioni, PAI, visite, documenti, magazzino e notifiche. Ogni pagina si apre, i moduli salvano i dati
giusti e rifiutano quelli sbagliati, i permessi dei ruoli sono rispettati.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from fasas.clinical.models import ClinicalEvent, ParameterReading, ParameterType, Restraint, Therapy
from fasas.core.models import SystemConfig
from fasas.core.shifts import resolve_shift
from fasas.daily.models import (
    ChecklistCheck,
    ChecklistItem,
    DailyRecord,
    DiaryEntry,
    EvacuationRecord,
    ShiftAssignment,
    ShiftClosure,
)
from fasas.daily.services import close_shift
from fasas.guests.models import AdmissionEvent, Allergy, ClinicalTag, Diagnosis, Guest, GuestContact
from fasas.notifications.models import Notification

from .base import FasasTestCase

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def now_input(delta=datetime.timedelta(0)):
    return (timezone.localtime() + delta).strftime("%Y-%m-%dT%H:%M")


class ScreenTestCase(FasasTestCase):
    def get_ok(self, url, user=None, contains=None):
        if user is not None:
            self.login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        if contains:
            self.assertContains(response, contains)
        return response

    def archive(self, guest=None):
        guest = guest or self.guest
        guest.status = Guest.Status.ARCHIVED
        guest.archived_at = timezone.now()
        guest.save()
        return guest


class GuestScreenTests(ScreenTestCase):
    def test_list_filters(self):
        tag = ClinicalTag.objects.create(name="Diabetico")
        self.guest.tags.add(tag)
        other = self.make_guest("BNCLRA90B41F205Z", first_name="Laura", last_name="Bianchi", room="12")
        self.archive(other)
        self.login(self.operator)
        url = reverse("guests:list")
        self.assertContains(self.get_ok(url), "Rossi")
        self.assertNotContains(self.client.get(url), "Bianchi Laura")
        self.assertContains(self.client.get(url, {"status": "archived"}), "Bianchi")
        self.assertContains(self.client.get(url, {"tag": tag.pk}), "Rossi")
        self.assertNotContains(self.client.get(url, {"q": "zzz"}), "RSSMRA80A01F205X")
        self.assertContains(self.client.get(url, {"q": "rss", "status": "active"}), "RSSMRA80A01F205X")

    def test_create_and_update_guest(self):
        self.login(self.coordinator)
        self.get_ok(reverse("guests:create"))
        data = {"last_name": "Verdi", "first_name": "Luigi", "sex": "M", "birth_date": "1975-02-12",
                "fiscal_code": "vrdlgu75b12h501a", "admission_date": timezone.localdate().isoformat()}
        response = self.client.post(reverse("guests:create"), data)
        guest = Guest.objects.get(last_name="Verdi")
        self.assertRedirects(response, guest.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(guest.fiscal_code, "VRDLGU75B12H501A")
        self.assertTrue(AdmissionEvent.objects.filter(guest=guest, kind="admission").exists())
        future = {**data, "fiscal_code": "VRDLGU75B12H501B", "birth_date": "2999-01-01"}
        self.assertContains(self.client.post(reverse("guests:create"), future), "non può essere futura")
        url = reverse("guests:update", args=[guest.pk])
        self.get_ok(url, contains="Modifica anagrafica")
        response = self.client.post(url, {**data, "room": "7B"})
        self.assertEqual(response.status_code, 302)
        guest.refresh_from_db()
        self.assertEqual(guest.room, "7B")
        self.archive(guest)
        self.assertRedirects(self.client.get(url), guest.get_absolute_url(), fetch_redirect_response=False)

    def test_detail_health_timeline(self):
        ParameterReading.objects.create(guest=self.guest, parameter_type=ParameterType.objects.get(code="temperatura"),
                                        value=Decimal("36.5"))
        ClinicalEvent.objects.create(guest=self.guest, event_type="fall", severity="low",
                                     description="Caduta in giardino")
        self.login(self.coordinator)
        self.get_ok(reverse("guests:detail", args=[self.guest.pk]), contains="Rossi")
        self.get_ok(reverse("guests:health", args=[self.guest.pk]), contains="Allergie")
        url = reverse("guests:timeline", args=[self.guest.pk])
        self.get_ok(url, contains="Caduta in giardino")
        self.assertNotContains(self.client.get(url, {"kind": "therapy"}), "Caduta in giardino")

    def test_contacts_diagnoses_allergies(self):
        self.login(self.coordinator)
        pk = self.guest.pk
        self.get_ok(reverse("guests:contact_create", args=[pk]))
        response = self.client.post(reverse("guests:contact_create", args=[pk]),
                                    {"kind": "guardian", "name": "Anna Rossi", "phone": "0212345"})
        self.assertRedirects(response, reverse("guests:health", args=[pk]), fetch_redirect_response=False)
        contact = GuestContact.objects.get()
        self.client.post(reverse("guests:contact_edit", args=[pk, contact.pk]),
                         {"kind": "guardian", "name": "Anna Rossi", "phone": "0299999"})
        contact.refresh_from_db()
        self.assertEqual(contact.phone, "0299999")
        self.client.post(reverse("guests:diagnosis_create", args=[pk]),
                         {"kind": "diagnosis", "description": "Disabilità intellettiva", "active": "on"})
        diagnosis = Diagnosis.objects.get()
        self.get_ok(reverse("guests:diagnosis_edit", args=[pk, diagnosis.pk]), contains="Disabilità intellettiva")
        self.client.post(reverse("guests:allergy_create", args=[pk]),
                         {"kind": "allergy", "category": "drug", "substance": "Penicillina", "severity": "severe"})
        allergy = Allergy.objects.get()
        self.get_ok(reverse("guests:allergy_edit", args=[pk, allergy.pk]), contains="Penicillina")
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("guests:allergy_create", args=[pk])).status_code, 403)
        self.login(self.coordinator)
        self.archive()
        self.assertRedirects(self.client.get(reverse("guests:diagnosis_create", args=[pk])),
                             reverse("guests:health", args=[pk]), fetch_redirect_response=False)

    def test_discharge_movement_and_tags(self):
        self.login(self.coordinator)
        tag = ClinicalTag.objects.create(name="Rischio caduta")
        url = reverse("guests:toggle_tag", args=[self.guest.pk, tag.pk])
        self.client.post(url)
        self.assertTrue(self.guest.tags.filter(pk=tag.pk).exists())
        self.client.post(url)
        self.assertFalse(self.guest.tags.filter(pk=tag.pk).exists())
        self.get_ok(reverse("guests:movement", args=[self.guest.pk]))
        self.client.post(reverse("guests:movement", args=[self.guest.pk]),
                         {"kind": "hospitalization", "date": timezone.localdate().isoformat(), "notes": "Pronto soccorso"})
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.status, Guest.Status.HOSPITALIZED)
        url = reverse("guests:discharge", args=[self.guest.pk])
        self.get_ok(url, contains="Dimetti e archivia")
        self.assertEqual(self.client.post(url, {"date": timezone.localdate().isoformat(), "reason": "Trasferito"})
                         .status_code, 200)  # manca la conferma
        self.client.post(url, {"date": timezone.localdate().isoformat(), "reason": "Trasferito", "confirm": "on"})
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.is_archived)
        self.assertRedirects(self.client.get(url), self.guest.get_absolute_url(), fetch_redirect_response=False)
        response = self.client.post(reverse("guests:movement", args=[self.guest.pk]),
                                    {"kind": "return", "date": timezone.localdate().isoformat()})
        self.assertEqual(response.status_code, 302)


class DailyScreenTests(ScreenTestCase):
    def test_shift_register(self):
        day, shift = resolve_shift()
        self.login(self.operator)
        url = reverse("daily:register")
        self.get_ok(url, contains="Registro")
        self.get_ok(f"{url}?date=non-una-data&shift=X")
        response = self.client.post(url, {"guest": self.guest.pk, "category": "behaviour",
                                          "occurred_at": now_input(), "description": "Sereno"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DailyRecord.objects.get().description, "Sereno")
        self.get_ok(f"{url}?date={day}&shift={shift}", contains="Sereno")
        close_shift(day, shift, self.coordinator)
        response = self.client.post(url, {"guest": self.guest.pk, "category": "behaviour",
                                          "occurred_at": now_input(), "description": "Dopo la chiusura"})
        self.assertContains(response, "chiuso")
        self.login(self.make_user("amm", "administrative"))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_records_evacuations_and_diary(self):
        self.login(self.operator)
        pk = self.guest.pk
        self.get_ok(reverse("daily:guest_daily", args=[pk]))
        self.get_ok(reverse("daily:record_create", args=[pk]) + "?category=meal&meal=lunch")
        self.client.post(reverse("daily:record_create", args=[pk]),
                         {"category": "meal", "meal": "lunch", "intake": "50", "occurred_at": now_input(),
                          "description": "Metà porzione"})
        record = DailyRecord.objects.get()
        self.get_ok(reverse("daily:record_update", args=[record.pk]))
        self.client.post(reverse("daily:record_update", args=[record.pk]),
                         {"category": "meal", "meal": "lunch", "intake": "75", "occurred_at": now_input()})
        record.refresh_from_db()
        self.assertEqual(record.intake, "75")

        self.get_ok(reverse("daily:evacuations"), contains="Rossi")
        response = self.client.post(reverse("daily:evacuation_quick", args=[pk]),
                                    {"outcome": "1", "next": "https://esterno.example/"})
        self.assertRedirects(response, reverse("daily:evacuations"), fetch_redirect_response=False)
        self.client.post(reverse("daily:evacuation_create", args=[pk]),
                         {"occurred_at": now_input(), "outcome": "on", "consistency": "4", "notes": "ok"})
        self.assertEqual(EvacuationRecord.objects.count(), 2)
        evacuation = EvacuationRecord.objects.latest("pk")
        self.get_ok(reverse("daily:evacuation_update", args=[evacuation.pk]))

        self.client.post(reverse("daily:diary_create", args=[pk]),
                         {"occurred_at": now_input(), "text": "Telefonata con la sorella", "is_relevant": "on"})
        entry = DiaryEntry.objects.get()
        self.get_ok(reverse("daily:guest_diary", args=[pk]) + "?relevant=1", contains="Telefonata con la sorella")
        self.get_ok(reverse("daily:diary_update", args=[entry.pk]))

        self.login(self.coordinator)
        for name, obj in (("daily:record_void", record), ("daily:evacuation_void", evacuation),
                          ("daily:diary_void", entry)):
            self.get_ok(reverse(name, args=[obj.pk]))
            self.client.post(reverse(name, args=[obj.pk]), {"reason": "Errore di inserimento"})
        self.assertFalse(DailyRecord.objects.exists())
        self.assertEqual(EvacuationRecord.objects.count(), 1)
        self.assertFalse(DiaryEntry.objects.exists())

    def test_evacuation_quick_on_closed_shift(self):
        day, shift = resolve_shift()
        close_shift(day, shift, self.coordinator)
        self.login(self.operator)
        self.client.post(reverse("daily:evacuation_quick", args=[self.guest.pk]), {"outcome": "0"})
        self.assertFalse(EvacuationRecord.objects.exists())

    def test_checklist(self):
        day, shift = resolve_shift()
        item = ChecklistItem.objects.filter(template__shift=shift).first() or ChecklistItem.objects.first()
        shift = item.template.shift
        self.login(self.operator)
        self.get_ok(f"{reverse('daily:checklist')}?date={day}&shift={shift}", contains=item.label)
        url = reverse("daily:checklist_toggle")
        response = self.client.post(url, {"date": "ieri"})
        self.assertRedirects(response, reverse("daily:checklist"), fetch_redirect_response=False)
        data = {"date": day.isoformat(), "shift": shift, "item": item.pk, "guest": self.guest.pk}
        self.client.post(url, {**data, "action": "done", "notes": "fatto"})
        self.assertTrue(ChecklistCheck.objects.filter(item=item).exists())
        self.client.post(url, {**data, "action": "undo"})
        self.assertFalse(ChecklistCheck.objects.filter(item=item).exists())
        self.client.post(url, {**data, "action": "na"})
        self.assertTrue(ChecklistCheck.objects.get(item=item).not_applicable)
        ChecklistCheck.objects.all().delete()
        close_shift(day, shift, self.coordinator)
        self.client.post(url, {**data, "action": "done"})
        self.assertFalse(ChecklistCheck.objects.exists())

    def test_roster_and_check_in(self):
        self.login(self.coordinator)
        url = reverse("daily:roster")
        self.get_ok(url + "?date=sbagliata")
        day, shift = resolve_shift()
        response = self.client.post(url, {"date": day.isoformat(), "shift": shift, "user": self.operator.pk})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ShiftAssignment.objects.filter(user=self.operator).exists())
        self.login(self.operator)
        self.assertRedirects(self.client.post(reverse("daily:check_in")), reverse("core:dashboard"),
                             fetch_redirect_response=False)
        self.assertIsNotNone(ShiftAssignment.objects.get(user=self.operator).checked_in_at)

    def test_closures_close_and_reopen(self):
        self.login(self.coordinator)
        self.get_ok(reverse("daily:closures"))
        day, shift = resolve_shift()
        tomorrow = day + datetime.timedelta(days=1)
        response = self.client.get(reverse("daily:close_shift"), {"date": tomorrow.isoformat(), "shift": "M"})
        self.assertRedirects(response, reverse("daily:closures"), fetch_redirect_response=False)
        url = f"{reverse('daily:close_shift')}?date={day}&shift={shift}"
        self.get_ok(url)
        response = self.client.post(url, {"handover_notes": "Tutto tranquillo", "confirm": "on"})
        closure = ShiftClosure.objects.get(date=day, shift=shift)
        self.assertRedirects(response, reverse("daily:closure_detail", args=[closure.pk]),
                             fetch_redirect_response=False)
        detail = reverse("daily:closure_detail", args=[closure.pk])
        self.get_ok(detail, contains="Tutto tranquillo")
        self.client.post(detail, {"reason": "Registrazione dimenticata"})
        closure.refresh_from_db()
        self.assertTrue(closure.is_closed)  # senza il permesso straordinario non si riapre
        self.coordinator.user_permissions.add(Permission.objects.get(codename="reopen_shift"))
        config = SystemConfig.get()
        config.allow_admin_reopen = True
        config.save()
        self.login(self.coordinator)
        self.client.post(detail, {"reason": "Registrazione dimenticata"})
        closure.refresh_from_db()
        self.assertFalse(closure.is_closed)


class ClinicalScreenTests(ScreenTestCase):
    def test_therapy_lifecycle(self):
        drug = self.make_drug()
        self.login(self.doctor)
        pk = self.guest.pk
        self.get_ok(reverse("clinical:therapy_create", args=[pk]) + "?sos=1")
        response = self.client.post(reverse("clinical:therapy_create", args=[pk]), {
            "drug": drug.pk, "dose": "1", "dose_unit": "cp", "stock_units_per_dose": "1", "route": "oral",
            "schedule_times": "08:00, 20:00", "every_n_days": "1", "start_date": timezone.localdate().isoformat(),
            "prescriber": self.doctor.pk, "prescription_date": timezone.localdate().isoformat()})
        therapy = Therapy.objects.get()
        self.assertRedirects(response, reverse("clinical:guest_therapies", args=[pk]), fetch_redirect_response=False)
        self.assertEqual(therapy.schedule_times, ["08:00", "20:00"])
        self.get_ok(reverse("clinical:guest_therapies", args=[pk]), contains="Tachipirina")
        self.get_ok(therapy.get_absolute_url(), contains="Tachipirina")
        self.get_ok(reverse("clinical:therapy_update", args=[therapy.pk]))
        self.get_ok(reverse("clinical:therapy_overview") + "?q=ros", contains="Tachipirina")
        self.client.post(reverse("clinical:therapy_status", args=[therapy.pk]),
                         {"status": "ended", "reason": "Ciclo concluso"})
        therapy.refresh_from_db()
        self.assertEqual(therapy.status, Therapy.Status.ENDED)
        self.assertEqual(therapy.end_date, timezone.localdate())
        self.assertRedirects(self.client.get(reverse("clinical:therapy_update", args=[therapy.pk])),
                             therapy.get_absolute_url(), fetch_redirect_response=False)
        self.archive()
        self.assertRedirects(self.client.get(reverse("clinical:therapy_create", args=[pk])),
                             self.guest.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(self.client.post(reverse("clinical:therapy_status", args=[therapy.pk]),
                                          {"status": "active", "reason": "x"}).status_code, 403)

    def test_duplicate_drug_needs_confirmation(self):
        therapy = self.make_therapy()
        self.login(self.doctor)
        data = {"drug": therapy.drug.pk, "dose": "1", "dose_unit": "cp", "stock_units_per_dose": "1", "route": "oral",
                "schedule_times": "13:00", "every_n_days": "1", "start_date": timezone.localdate().isoformat(),
                "prescriber_name": "Dott. Test", "prescription_date": timezone.localdate().isoformat()}
        response = self.client.post(reverse("clinical:therapy_create", args=[self.guest.pk]), data)
        self.assertContains(response, "verificarli e confermare")
        self.client.post(reverse("clinical:therapy_create", args=[self.guest.pk]), {**data, "confirm_warnings": "on"})
        self.assertEqual(Therapy.objects.count(), 2)
        self.assertTrue(Therapy.objects.latest("pk").conflict_acknowledged)

    def test_sos_validation_and_administrations(self):
        therapy = self.make_therapy(is_sos=True, schedule_times=[], sos_indication="Dolore",
                                    sos_requires_validation=True)
        self.login(self.operator)
        response = self.client.post(reverse("clinical:sos_administer", args=[self.guest.pk]), {
            "therapy": therapy.pk, "occurred_at": now_input(), "sos_reason": "Mal di testa"})
        self.assertEqual(response.status_code, 302)
        self.login(self.doctor)
        self.get_ok(reverse("clinical:sos_pending"), contains="Mal di testa")
        from fasas.clinical.models import TherapyAdministration

        adm = TherapyAdministration.objects.get()
        self.client.post(reverse("clinical:sos_validate", args=[adm.pk]), {"approve": "1", "notes": "ok"})
        adm.refresh_from_db()
        self.assertEqual(adm.validation_status, TherapyAdministration.Validation.VALIDATED)
        self.login(self.coordinator)
        self.get_ok(reverse("clinical:guest_administrations", args=[self.guest.pk])
                    + f"?date={adm.shift_date}", contains="Mal di testa")
        url = reverse("clinical:administration_void", args=[adm.pk])
        self.get_ok(url)
        self.client.post(url, {"reason": "Registrata due volte"})
        self.assertFalse(TherapyAdministration.objects.exists())

    def test_parameters(self):
        self.login(self.operator)
        pk = self.guest.pk
        temperature = ParameterType.objects.get(code="temperatura")
        url = reverse("clinical:quick_parameters", args=[pk])
        self.get_ok(url)
        self.assertContains(self.client.post(url, {"occurred_at": now_input()}), "almeno un valore")
        response = self.client.post(url, {"occurred_at": now_input(), f"p_{temperature.pk}": "36.8"})
        self.assertRedirects(response, reverse("clinical:guest_parameters", args=[pk]), fetch_redirect_response=False)
        reading = ParameterReading.objects.get()
        self.client.post(reverse("clinical:parameter_create", args=[pk]),
                         {"parameter_type": temperature.pk, "occurred_at": now_input(), "value": "37.1"})
        self.assertEqual(ParameterReading.objects.count(), 2)
        params = reverse("clinical:guest_parameters", args=[pk])
        self.get_ok(params + "?days=molti", contains="Temperatura")
        self.get_ok(params + f"?days=30&type={temperature.pk}")
        self.get_ok(reverse("clinical:parameter_update", args=[reading.pk]))
        self.client.post(reverse("clinical:parameter_update", args=[reading.pk]),
                         {"parameter_type": temperature.pk, "occurred_at": now_input(), "value": "36.9"})
        reading.refresh_from_db()
        self.assertEqual(reading.value, Decimal("36.9"))
        self.login(self.coordinator)
        self.client.post(reverse("clinical:parameter_void", args=[reading.pk]), {"reason": "Termometro guasto"})
        self.assertEqual(ParameterReading.objects.count(), 1)

    def test_events_emergency_and_restraints(self):
        self.login(self.operator)
        pk = self.guest.pk
        self.get_ok(reverse("clinical:event_create", args=[pk]) + "?type=fall")
        self.client.post(reverse("clinical:event_create", args=[pk]), {
            "event_type": "fall", "severity": "low", "occurred_at": now_input(), "description": "Scivolato in bagno"})
        event = ClinicalEvent.objects.get()
        self.get_ok(reverse("clinical:guest_events", args=[pk]) + "?type=fall", contains="Scivolato in bagno")
        self.get_ok(reverse("clinical:event_detail", args=[event.pk]), contains="Scivolato in bagno")
        self.get_ok(reverse("clinical:event_update", args=[event.pk]))
        self.get_ok(reverse("clinical:emergency") + f"?guest={pk}")
        response = self.client.post(reverse("clinical:emergency"), {
            "guest": pk, "event_type": "seizure", "description": "Crisi tonico-clonica", "actions_taken": "Posizione"})
        emergency = ClinicalEvent.objects.get(is_emergency=True)
        self.assertRedirects(response, reverse("clinical:event_detail", args=[emergency.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(emergency.severity, ClinicalEvent.Severity.CRITICAL)
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator).exists())

        self.login(self.coordinator)
        url = reverse("clinical:restraint_create", args=[pk])
        self.get_ok(url)
        self.client.post(url, {
            "restraint_type": "bed_rails", "occurred_at": now_input(), "reason": "Rischio caduta notturna",
            "alternatives_tried": "Letto basso", "authorized_by": self.doctor.pk,
            "authorization_date": timezone.localdate().isoformat(), "responsible_operator": self.operator.pk})
        restraint = Restraint.objects.get()
        self.get_ok(reverse("clinical:restraint_update", args=[restraint.pk]))
        for name, obj in (("clinical:event_void", event), ("clinical:restraint_void", restraint)):
            self.client.post(reverse(name, args=[obj.pk]), {"reason": "Inserita per errore"})
        self.assertFalse(Restraint.objects.exists())
        self.assertEqual(ClinicalEvent.objects.count(), 1)

    def test_emergency_on_archived_guest_is_refused(self):
        self.login(self.operator)
        other = self.make_guest("BNCLRA90B41F205Z", first_name="Laura", last_name="Bianchi")
        self.client.get(reverse("clinical:emergency"))
        self.archive(other)
        response = self.client.post(reverse("clinical:emergency"), {
            "guest": other.pk, "event_type": "fall", "description": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ClinicalEvent.objects.exists())


class PaiScreenTests(ScreenTestCase):
    def test_pai_from_draft_to_revision(self):
        self.login(self.coordinator)
        pk = self.guest.pk
        self.get_ok(reverse("pai:guest", args=[pk]), contains="PAI")
        self.client.post(reverse("pai:create", args=[pk]))
        from fasas.pai.models import PAI, PAIGoal

        pai = PAI.objects.get()
        self.assertRedirects(self.client.get(reverse("pai:guest", args=[pk])), pai.get_absolute_url(),
                             fetch_redirect_response=False)
        self.client.post(reverse("pai:create", args=[pk]))  # esiste già: messaggio di errore
        self.assertEqual(PAI.objects.count(), 1)
        self.get_ok(reverse("pai:edit", args=[pai.pk]))
        self.client.post(reverse("pai:edit", args=[pai.pk]), {
            "review_due": (timezone.localdate() + datetime.timedelta(days=180)).isoformat(),
            "summary": "Bisogni rilevati", "participants": "Équipe e tutore"})
        self.get_ok(reverse("pai:goal_create", args=[pai.pk]) + "?area=health")
        self.client.post(reverse("pai:goal_create", args=[pai.pk]), {
            "area": "health", "objective": "Ridurre le cadute", "intervention": "Accompagnamento", "order": 1,
            "verification_date": (timezone.localdate() + datetime.timedelta(days=90)).isoformat()})
        goal = PAIGoal.objects.get()
        self.client.post(reverse("pai:goal_edit", args=[pai.pk, goal.pk]), {
            "area": "health", "objective": "Ridurre le cadute notturne", "intervention": "Luce notturna", "order": 1,
            "verification_date": (timezone.localdate() + datetime.timedelta(days=90)).isoformat()})
        goal.refresh_from_db()
        self.assertEqual(goal.objective, "Ridurre le cadute notturne")
        extra = PAIGoal.objects.create(pai=pai, area="social", objective="Uscite", intervention="Gita",
                                       verification_date=timezone.localdate())
        self.client.post(reverse("pai:goal_delete", args=[pai.pk, extra.pk]))
        self.assertEqual(PAIGoal.objects.count(), 1)

        self.client.post(reverse("pai:activate", args=[pai.pk]))
        pai.refresh_from_db()
        self.assertEqual(pai.status, PAI.Status.ACTIVE)
        self.assertIsNotNone(pai.document)
        self.assertEqual(self.client.get(reverse("pai:edit", args=[pai.pk])).status_code, 403)
        url = reverse("pai:goal_verify", args=[pai.pk, goal.pk])
        self.get_ok(url)
        self.client.post(url, {"outcome": "partial", "verification_notes": "Meno cadute",
                               "verification_date": timezone.localdate().isoformat()})
        goal.refresh_from_db()
        self.assertEqual(goal.outcome, "partial")
        response = self.client.post(reverse("pai:pdf", args=[pai.pk]))
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse("pai:revise", args=[pai.pk]))
        self.assertEqual(PAI.objects.filter(status=PAI.Status.DRAFT).count(), 1)
        self.client.post(reverse("pai:revise", args=[pai.pk]))  # una sola bozza alla volta
        self.assertEqual(PAI.objects.count(), 2)

    def test_operator_cannot_change_pai(self):
        from fasas.pai.services import create_first

        pai = create_first(self.guest, self.coordinator, timezone.localdate() + datetime.timedelta(days=90))
        self.login(self.operator)
        self.get_ok(pai.get_absolute_url())
        self.assertEqual(self.client.get(reverse("pai:edit", args=[pai.pk])).status_code, 403)
        self.client.post(reverse("pai:activate", args=[pai.pk]))
        pai.refresh_from_db()
        self.assertEqual(pai.status, "draft")


class AppointmentScreenTests(ScreenTestCase):
    def test_appointments(self):
        self.login(self.coordinator)
        self.get_ok(reverse("appointments:create") + f"?guest={self.guest.pk}&kind=exam")
        when = (timezone.localtime() + datetime.timedelta(days=2)).replace(hour=10, minute=0)
        self.client.post(reverse("appointments:create"), {
            "guest": self.guest.pk, "kind": "exam", "title": "Prelievo", "scheduled_at": when.strftime("%Y-%m-%dT%H:%M"),
            "location": "Ospedale"})
        from fasas.appointments.models import Appointment

        appointment = Appointment.objects.get()
        url = reverse("appointments:list")
        self.get_ok(url, contains="Prelievo")
        self.get_ok(url + f"?guest={self.guest.pk}&kind=exam", contains="Prelievo")
        self.assertNotContains(self.client.get(url + "?period=past"), "Prelievo")
        self.get_ok(reverse("appointments:guest_list", args=[self.guest.pk]), contains="Prelievo")
        self.get_ok(appointment.get_absolute_url(), contains="Prelievo")
        appointment.reminded_day_before = True
        appointment.save()
        later = when + datetime.timedelta(days=1)
        self.client.post(reverse("appointments:update", args=[appointment.pk]), {
            "guest": self.guest.pk, "kind": "exam", "title": "Prelievo", "scheduled_at": later.strftime("%Y-%m-%dT%H:%M"),
            "location": "Ospedale"})
        appointment.refresh_from_db()
        self.assertFalse(appointment.reminded_day_before)  # nuova data: promemoria da reinviare
        url = reverse("appointments:outcome", args=[appointment.pk])
        self.get_ok(url)
        self.client.post(url, {"status": "done", "outcome": "Valori nella norma"})
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "done")


class DocumentScreenTests(ScreenTestCase):
    def test_upload_view_edit_new_version(self):
        self.login(self.coordinator)
        pk = self.guest.pk
        url = reverse("documents:create", args=[pk])
        self.get_ok(url + "?category=consent")
        self.client.post(url, {"category": "consent", "title": "Consenso trattamento",
                               "file": SimpleUploadedFile("consenso.pdf", PDF, content_type="application/pdf")})
        from fasas.documents.models import Document

        document = Document.objects.get()
        self.get_ok(reverse("documents:guest_list", args=[pk]) + "?category=consent", contains="Consenso trattamento")
        self.get_ok(document.get_absolute_url(), contains="consenso.pdf")
        version = document.current_version
        view = self.client.get(reverse("documents:view", args=[version.pk]))
        self.assertEqual(view["Content-Type"], "application/pdf")
        self.assertEqual(view["Cache-Control"], "no-store")
        download = self.client.get(reverse("documents:download", args=[version.pk]))
        self.assertIn("attachment", download["Content-Disposition"])
        self.get_ok(reverse("documents:edit", args=[document.pk]))
        self.client.post(reverse("documents:edit", args=[document.pk]),
                         {"category": "consent", "title": "Consenso firmato"})
        document.refresh_from_db()
        self.assertEqual(document.title, "Consenso firmato")
        self.client.post(reverse("documents:version_upload", args=[document.pk]), {
            "file": SimpleUploadedFile("consenso-v2.pdf", PDF, content_type="application/pdf"), "note": "firmato"})
        self.assertEqual(document.versions.count(), 2)
        self.client.post(url, {"category": "other", "title": "Script",
                               "file": SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream")})
        self.assertEqual(Document.objects.count(), 1)  # estensione non ammessa
        self.archive()
        self.assertRedirects(self.client.get(url), self.guest.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("documents:edit", args=[document.pk])).status_code, 403)

    def test_administrative_cannot_open_health_documents(self):
        from fasas.documents.services import create_document

        document = create_document(self.guest, "medical_report", "Relazione", user=self.coordinator, data=PDF,
                                   filename="relazione.pdf")
        self.login(self.make_user("amm", "administrative"))
        self.assertEqual(self.client.get(reverse("documents:view", args=[document.current_version.pk])).status_code,
                         403)


class PharmacyScreenTests(ScreenTestCase):
    def test_stock_load_and_adjust(self):
        drug = self.make_drug(min_stock=10)
        self.login(self.coordinator)
        url = reverse("pharmacy:lot_load")
        self.get_ok(url + f"?drug={drug.pk}")
        self.client.post(url, {"drug": drug.pk, "lot_number": "L123", "expiry_date": "2030-01-31",
                               "quantity": "5", "supplier": "Farmacia"})
        from fasas.pharmacy.models import StockLot

        lot = StockLot.objects.get()
        stock = reverse("pharmacy:stock")
        self.get_ok(stock, contains="Tachipirina")
        self.get_ok(stock + "?status=low", contains="Tachipirina")
        self.assertNotContains(self.client.get(stock + "?status=expiring"), "L123")
        self.assertNotContains(self.client.get(stock + "?q=aspirina"), "Tachipirina")
        detail = reverse("pharmacy:lot_detail", args=[lot.pk])
        self.get_ok(detail, contains="L123")
        self.client.post(detail, {"kind": "adjustment", "new_quantity": "3", "notes": "Conteggio"})
        lot.refresh_from_db()
        self.assertEqual(lot.quantity, Decimal("3"))
        self.login(self.operator)
        self.assertEqual(self.client.get(stock).status_code, 403)


class NotificationScreenTests(ScreenTestCase):
    def test_list_read_and_count(self):
        first = Notification.objects.create(recipient=self.operator, kind="system_error", title="Primo",
                                            message="m", link="/ospiti/")
        Notification.objects.create(recipient=self.operator, kind="system_error", title="Critico", message="m",
                                    level=Notification.Level.CRITICAL)
        self.login(self.operator)
        self.get_ok(reverse("notifications:list") + "?unread=1", contains="Primo")
        count = self.client.get(reverse("notifications:count")).json()
        self.assertEqual(count["count"], 2)
        self.assertEqual(count["critical"]["title"], "Critico")
        response = self.client.post(reverse("notifications:mark_read", args=[first.pk]),
                                    {"next": "https://esterno.example/"})
        self.assertRedirects(response, reverse("notifications:list"), fetch_redirect_response=False)
        first.refresh_from_db()
        self.assertIsNotNone(first.read_at)
        response = self.client.post(reverse("notifications:mark_read", args=[first.pk]), {"open": "1"})
        self.assertRedirects(response, "/ospiti/", fetch_redirect_response=False)
        self.client.post(reverse("notifications:mark_all_read"))
        self.assertEqual(self.client.get(reverse("notifications:count")).json()["count"], 0)
        other = Notification.objects.create(recipient=self.coordinator, kind="system_error", title="Altrui",
                                            message="m")
        self.assertEqual(self.client.post(reverse("notifications:mark_read", args=[other.pk])).status_code, 404)
        self.get_ok(reverse("notifications:devices"))
