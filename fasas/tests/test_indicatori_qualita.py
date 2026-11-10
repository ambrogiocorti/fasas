"""Indicatori di qualità mese per mese: conteggi, giornate di presenza, frequenze, annullate escluse, permessi."""
import datetime

from django.urls import reverse
from django.utils import timezone

from fasas.audit.context import audit_context
from fasas.clinical.models import ClinicalEvent, Restraint
from fasas.guests.models import AdmissionEvent
from fasas.reports import quality
from fasas.wounds.models import Wound

from .base import FasasTestCase


class IndicatoriQualitaTest(FasasTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        noon = timezone.make_aware(datetime.datetime.combine(self.today, datetime.time(12)))
        with audit_context(user=self.operator):
            ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="Caduta in bagno",
                                         occurred_at=noon)
            ClinicalEvent.objects.create(guest=self.guest, event_type="fall", severity="high",
                                         description="Caduta dal letto", injuries="Ematoma", occurred_at=noon)
            voided = ClinicalEvent.objects.create(guest=self.guest, event_type="fall", description="Errore",
                                                  occurred_at=noon)
            voided.voided_at, voided.void_reason = timezone.now(), "Registrata per errore"
            voided.save()
            Wound.objects.create(guest=self.guest, kind="pressure", site="sacrum", origin="in_house", occurred_at=noon)
            Wound.objects.create(guest=self.guest, kind="pressure", site="heel", origin="admission", occurred_at=noon)
            Restraint.objects.create(guest=self.guest, restraint_type="bed_rails", reason="Rischio caduta notturna",
                                     authorization_date=self.today, authorizing_doctor_name="Dott. Prova",
                                     responsible_operator=self.operator, occurred_at=noon)
            AdmissionEvent.objects.create(guest=self.guest, kind="hospitalization", date=self.today)

    def test_conteggi_del_mese(self):
        data = quality.monthly(today=self.today)
        self.assertEqual(len(data["months"]), 12)
        self.assertEqual(data["months"][-1], self.today.replace(day=1))
        by_key = {i.key: i for i in data["indicators"]}
        self.assertEqual(by_key["falls"].values[-1], 2)  # l'annullata non conta
        self.assertEqual(by_key["falls_injury"].values[-1], 1)
        self.assertEqual(by_key["serious"].values[-1], 1)
        self.assertEqual(by_key["pressure"].values[-1], 1)  # quella presente all'ingresso non conta
        self.assertEqual(by_key["restraints"].values[-1], 1)
        self.assertEqual(by_key["restraint_guests"].values[-1], 1)
        self.assertEqual(by_key["hospital"].values[-1], 1)
        days = data["guest_days"][-1]
        self.assertGreater(days, 0)
        self.assertEqual(by_key["falls"].rates[-1], round(2 * 1000 / days, 2))
        self.assertEqual(by_key["restraint_guests"].rates[-1], 100.0)

    def test_giornate_di_presenza(self):
        first = datetime.date(2026, 3, 1)
        self.make_guest("VRDLGU40A01F205Z", admission_date=datetime.date(2026, 3, 11),
                        discharge_date=datetime.date(2026, 3, 20))
        days, guests = quality.guest_days([first], datetime.date(2026, 3, 31))
        self.assertEqual(days[first], 10 + (31 if self.guest.admission_date <= first else 0))

    def test_pagina_csv_e_permessi(self):
        self.login(self.coordinator)
        page = self.client.get(reverse("reports:quality"))
        self.assertContains(page, "Cadute con conseguenze")
        csv = self.client.get(reverse("reports:quality"), {"formato": "csv"}).content.decode("utf-8-sig")
        self.assertIn("Giornate di presenza", csv)
        self.login(self.doctor)
        self.assertEqual(self.client.get(reverse("reports:quality")).status_code, 200)
        for user in (self.operator, self.admin):
            self.login(user)
            self.assertEqual(self.client.get(reverse("reports:quality")).status_code, 403)
