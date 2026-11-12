"""Scadenze del personale: stato per dipendente, calcolo della scadenza, avvisi, attestati cifrati, permessi."""
import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from fasas.accounts.models import Role
from fasas.notifications.models import Notification
from fasas.staffing import credentials as services
from fasas.staffing.models import CredentialType, StaffCredential

from .base import FasasTestCase

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class ScadenzePersonaleTest(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.office = cls.make_user("uff", Role.ADMINISTRATIVE)
        cls.blsd = CredentialType.objects.get(name__startswith="BLSD")
        cls.fire = CredentialType.objects.get(name__startswith="Antincendio")
        cls.fitness = CredentialType.objects.get(name__startswith="Idoneità")

    def test_tipi_proposti_e_calcolo_scadenza(self):
        self.assertGreaterEqual(CredentialType.objects.count(), 7)
        self.assertEqual(services.add_months(datetime.date(2024, 1, 31), 1), datetime.date(2024, 2, 29))
        self.assertEqual(services.add_months(datetime.date(2024, 11, 15), 24), datetime.date(2026, 11, 15))
        credential = services.add_credential(self.operator, self.blsd, datetime.date(2025, 3, 10), self.coordinator)
        self.assertEqual(credential.expires_on, datetime.date(2027, 3, 10))
        with self.assertRaisesMessage(services.CredentialError, "futuro"):
            services.add_credential(self.operator, self.blsd, timezone.localdate() + datetime.timedelta(days=1),
                                    self.coordinator)
        with self.assertRaisesMessage(services.CredentialError, "precede"):
            services.add_credential(self.operator, self.fitness, datetime.date(2025, 3, 10), self.coordinator,
                                    expires_on=datetime.date(2025, 1, 1))

    def test_stati(self):
        today = timezone.localdate()
        services.add_credential(self.operator, self.blsd, today - datetime.timedelta(days=800), self.coordinator)
        services.add_credential(self.operator, self.fitness, today - datetime.timedelta(days=300), self.coordinator,
                                expires_on=today + datetime.timedelta(days=20))
        data = services.matrix([self.operator])
        cells = {c.type.pk: c for c in data["rows"][0]["cells"]}
        self.assertEqual(cells[self.blsd.pk].status, "expired")
        self.assertEqual(cells[self.fitness.pk].status, "expiring")
        self.assertEqual(cells[self.fire.pk].status, "none")  # solo per gli addetti designati
        sicurezza = CredentialType.objects.get(name__startswith="Sicurezza")
        self.assertEqual(cells[sicurezza.pk].status, "missing")
        # un nuovo attestato sostituisce il precedente
        services.add_credential(self.operator, self.blsd, today, self.coordinator)
        cells = {c.type.pk: c for c in services.matrix([self.operator])["rows"][0]["cells"]}
        self.assertEqual(cells[self.blsd.pk].status, "valid")

    def test_avvisi(self):
        today = timezone.localdate()
        services.add_credential(self.operator, self.blsd, today - datetime.timedelta(days=800), self.coordinator)
        result = services.reminders(today)
        self.assertGreater(result["problems"], 0)
        self.assertTrue(Notification.objects.filter(recipient=self.coordinator, kind="staff_deadlines").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.office, kind="staff_deadlines").exists())
        mine = Notification.objects.filter(recipient=self.operator, kind="my_deadline")
        self.assertTrue(mine.filter(title__contains="BLSD").exists())
        # il dipendente riceve solo le proprie scadenze, il medico non riceve il riepilogo
        self.assertFalse(Notification.objects.filter(recipient=self.doctor, kind="staff_deadlines").exists())
        before = Notification.objects.count()
        services.reminders(today)
        self.assertEqual(Notification.objects.count(), before)

    def test_pagine_e_attestato(self):
        self.login(self.office)
        self.assertEqual(self.client.get(reverse("staffing:credentials")).status_code, 200)
        response = self.client.post(reverse("staffing:credential_create"), {
            "user": self.operator.pk, "type": self.blsd.pk, "obtained_on": timezone.localdate().isoformat(),
            "provider": "Croce di prova", "certificate": SimpleUploadedFile("blsd.pdf", PDF, "application/pdf")})
        self.assertEqual(response.status_code, 302, response.content.decode()[:400])
        credential = StaffCredential.objects.get(user=self.operator, type=self.blsd)
        self.assertEqual(credential.certificate_type, "application/pdf")
        csv = self.client.get(reverse("staffing:credentials"), {"formato": "csv"})
        self.assertIn("BLSD", csv.content.decode("utf-8-sig"))
        # il dipendente vede le proprie scadenze e il proprio attestato, non il quadro di tutti
        self.login(self.operator)
        page = self.client.get(reverse("staffing:my_credentials"))
        self.assertContains(page, "BLSD")
        self.assertEqual(self.client.get(reverse("staffing:credential_file", args=[credential.pk])).content, PDF)
        self.assertEqual(self.client.get(reverse("staffing:credentials")).status_code, 403)
        self.login(self.doctor)
        self.assertEqual(self.client.get(reverse("staffing:credential_file", args=[credential.pk])).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("staffing:credentials")).status_code, 403)

    def test_tipi_modificabili(self):
        self.login(self.coordinator)
        response = self.client.post(reverse("staffing:credential_type_update", args=[self.fire.pk]), {
            "name": self.fire.name, "category": "training", "validity_months": "60", "warn_days": "90",
            "roles": ["operator"], "reference": "", "active": "on", "order": "20"})
        self.assertEqual(response.status_code, 302)
        self.fire.refresh_from_db()
        self.assertEqual((self.fire.warn_days, self.fire.roles), (90, ["operator"]))
