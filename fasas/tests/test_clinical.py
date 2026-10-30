import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from fasas.clinical.models import TherapyAdministration
from fasas.clinical.services import (
    check_therapy_conflicts,
    register_administration,
    scheduled_doses,
    void_administration,
)
from fasas.core.shifts import Shift
from fasas.guests.models import Allergy
from fasas.notifications.models import Notification
from fasas.pharmacy.models import DrugInteraction
from fasas.pharmacy.services import load_lot

from .base import FasasTestCase


class TherapyConflictTests(FasasTestCase):
    def test_duplicate_same_drug_and_ingredient(self):
        drug = self.make_drug()
        self.make_therapy(drug=drug)
        kinds = [w.kind for w in check_therapy_conflicts(self.guest, drug)]
        self.assertIn("duplicate", kinds)
        generic = self.make_drug(name="Paracetamolo generico", ingredient="Paracetamolo")
        warnings = check_therapy_conflicts(self.guest, generic)
        self.assertTrue(any("principio attivo" in w.message for w in warnings))

    def test_interaction_from_table(self):
        from fasas.core.models import SystemConfig

        self.make_therapy(drug=self.make_drug("Coumadin", "warfarin", "B01AA03"))
        interaction = DrugInteraction.objects.create(ingredient_a="warfarin", ingredient_b="acido acetilsalicilico",
                                                     severity="major", description="Rischio emorragico")
        aspirin = self.make_drug("Cardioaspirin", "acido acetilsalicilico", "B01AC06")
        self.assertEqual(check_therapy_conflicts(self.guest, aspirin), [])  # spenti finché c'è il parere MDR
        SystemConfig.objects.update(therapy_check_interactions=True)
        self.assertEqual(check_therapy_conflicts(self.guest, aspirin), [])  # regola non ancora validata dal medico
        self.login(self.coordinator)
        self.assertEqual(self.client.post(reverse("pharmacy:interaction_validate", args=[interaction.pk])).status_code,
                         403)
        self.login(self.doctor)
        self.assertContains(self.client.get(reverse("pharmacy:interaction_list")), "DA VALIDARE")
        self.client.post(reverse("pharmacy:interaction_validate", args=[interaction.pk]))
        warnings = check_therapy_conflicts(self.guest, aspirin)
        self.assertEqual([w.kind for w in warnings], ["interaction"])
        self.assertEqual(warnings[0].level, "danger")
        # modificare la regola la toglie dai promemoria finché il medico non la rivalida
        self.client.post(reverse("pharmacy:interaction_update", args=[interaction.pk]), {
            "ingredient_a": "warfarin", "ingredient_b": "acido acetilsalicilico", "severity": "moderate",
            "description": "Rischio emorragico", "source": ""})
        interaction.refresh_from_db()
        self.assertFalse(interaction.is_validated)
        self.assertEqual(check_therapy_conflicts(self.guest, aspirin), [])

    def test_checks_can_be_switched_off(self):
        from fasas.core.models import SystemConfig

        drug = self.make_drug()
        self.make_therapy(drug=drug)
        Allergy.objects.create(guest=self.guest, substance="paracetamolo", category="drug")
        SystemConfig.objects.update(therapy_check_duplicates=False, therapy_check_allergies=False)
        self.assertEqual(check_therapy_conflicts(self.guest, drug), [])

    def test_allergy_warning(self):
        Allergy.objects.create(guest=self.guest, substance="paracetamolo", category="drug")
        warnings = check_therapy_conflicts(self.guest, self.make_drug())
        self.assertTrue(any(w.kind == "allergy" for w in warnings))

    def test_form_requires_confirmation_and_notifies(self):
        Allergy.objects.create(guest=self.guest, substance="paracetamolo", category="drug")
        drug = self.make_drug()
        self.login(self.coordinator)
        url = f"/sanitario/ospite/{self.guest.pk}/terapie/nuova/"
        data = {"drug": drug.pk, "dose": "1", "dose_unit": "cp", "stock_units_per_dose": "1", "route": "oral",
                "schedule_times": "8, 20:00", "every_n_days": "1", "start_date": timezone.localdate().isoformat(),
                "prescription_date": timezone.localdate().isoformat(), "prescriber_name": "Dott. Rossi",
                "sos_requires_validation": "on"}
        response = self.client.post(url, data)
        self.assertContains(response, "ALLERGIA registrata")
        self.assertFalse(self.guest.therapies.exists())
        response = self.client.post(url, {**data, "confirm_warnings": "on"})
        self.assertEqual(response.status_code, 302)
        therapy = self.guest.therapies.get()
        self.assertEqual(therapy.schedule_times, ["08:00", "20:00"])
        self.assertIn("ALLERGIA", therapy.conflict_acknowledged)
        self.assertTrue(Notification.objects.filter(kind="therapy_conflict", level="critical").exists())

    def test_operator_cannot_prescribe(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(f"/sanitario/ospite/{self.guest.pk}/terapie/nuova/").status_code, 403)


class AdministrationTests(FasasTestCase):
    def test_scheduled_doses_in_shift(self):
        therapy = self.make_therapy(schedule_times=["08:00", "13:00", "20:00", "02:00"])
        day = timezone.localdate()
        morning = scheduled_doses(day, Shift.MORNING)
        self.assertEqual([d.time.strftime("%H:%M") for d in morning], ["08:00", "13:00"])
        night = scheduled_doses(day, Shift.NIGHT)
        self.assertEqual([d.time.strftime("%H:%M") for d in night], ["02:00"])
        self.assertEqual(night[0].day, day + datetime.timedelta(days=1))
        self.assertTrue(all(d.therapy == therapy for d in morning))

    def test_administration_unloads_stock_fefo_personal_first(self):
        drug = self.make_drug(min_stock=5)
        therapy = self.make_therapy(drug=drug, stock_units_per_dose=Decimal("2"))
        today = timezone.localdate()
        community_lot = load_lot(drug, "C1", today + datetime.timedelta(days=10), 10, self.coordinator)
        personal_lot = load_lot(drug, "P1", today + datetime.timedelta(days=300), 1, self.coordinator, guest=self.guest)
        expired = load_lot(drug, "OLD", today - datetime.timedelta(days=1), 50, self.coordinator)
        adm = register_administration(therapy, self.operator, scheduled_date=today,
                                      scheduled_time=datetime.time(8, 0))
        for lot in (personal_lot, community_lot, expired):
            lot.refresh_from_db()
        self.assertEqual(personal_lot.quantity, Decimal("0"))  # prima il farmaco personale
        self.assertEqual(community_lot.quantity, Decimal("9"))
        self.assertEqual(expired.quantity, Decimal("50"))  # mai lotti scaduti
        void_administration(adm, self.coordinator, "Registrata per errore")
        personal_lot.refresh_from_db()
        community_lot.refresh_from_db()
        self.assertEqual(personal_lot.quantity + community_lot.quantity, Decimal("11"))

    def test_low_stock_notification(self):
        drug = self.make_drug(min_stock=5)
        therapy = self.make_therapy(drug=drug)
        load_lot(drug, "C1", timezone.localdate() + datetime.timedelta(days=100), 5, self.coordinator)
        register_administration(therapy, self.operator)
        self.assertTrue(Notification.objects.filter(kind="stock_low", recipient=self.coordinator).exists())

    def test_sos_requires_validation_when_given_by_operator(self):
        sos = self.make_therapy(is_sos=True, schedule_times=[], sos_indication="Febbre", sos_requires_validation=True)
        adm = register_administration(sos, self.operator, sos_reason="TC 38.4")
        self.assertEqual(adm.validation_status, TherapyAdministration.Validation.PENDING)
        self.assertTrue(Notification.objects.filter(kind="sos_validation", recipient=self.coordinator).exists())
        adm2 = register_administration(sos, self.doctor, sos_reason="TC 38.6")
        self.assertEqual(adm2.validation_status, TherapyAdministration.Validation.VALIDATED)

    def test_board_post_registers_dose_once(self):
        therapy = self.make_therapy(schedule_times=["08:00"])
        self.login(self.operator)
        data = {"day": timezone.localdate().isoformat(), "time": "08:00", "status": "given"}
        self.client.post(f"/sanitario/terapia/{therapy.pk}/somministra/", data)
        self.client.post(f"/sanitario/terapia/{therapy.pk}/somministra/", data)
        self.assertEqual(TherapyAdministration.objects.filter(therapy=therapy).count(), 1)

    def test_closed_shift_rejects_new_records(self):
        from fasas.core.shifts import resolve_shift
        from fasas.daily.services import close_shift

        day, shift = resolve_shift()
        close_shift(day, shift, self.operator)
        self.login(self.operator)
        response = self.client.post(f"/sanitario/ospite/{self.guest.pk}/eventi/nuovo/", {
            "event_type": "fall", "severity": "low", "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "description": "Caduta"})
        self.assertContains(response, "Il turno di riferimento è chiuso")

    def test_emergency_creates_critical_notification(self):
        self.login(self.operator)
        response = self.client.post("/sanitario/emergenza/", {
            "guest": self.guest.pk, "event_type": "emergency", "description": "Ospite non risponde", "actions_taken": "118"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(kind="emergency_event", level="critical",
                                                    recipient=self.coordinator).exists())
