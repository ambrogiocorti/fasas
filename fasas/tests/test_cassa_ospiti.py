"""Denaro e oggetti personali degli ospiti: saldo, scontrini cifrati, annullamenti, rendiconto, permessi."""
import datetime
import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from fasas.accounts.models import Role
from fasas.audit.models import AuditLog
from fasas.personal import services
from fasas.personal.models import CashMovement, PersonalItem

from .base import FasasTestCase


def photo(name="scontrino.jpg"):
    buffer = io.BytesIO()
    image = Image.new("RGB", (900, 1400), (240, 240, 230))
    exif = Image.Exif()
    exif[0x010F] = "Telefono di prova"  # marca: non deve restare nel file salvato
    image.save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class CassaOspitiTest(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.office = cls.make_user("uff", Role.ADMINISTRATIVE)

    def test_saldo_e_saldo_insufficiente(self):
        services.add_movement(self.guest, self.office, "deposit", "100.00", "Versamento della sorella",
                              counterpart="Anna Rossi")
        services.add_movement(self.guest, self.operator, "expense", "12.50", "Parrucchiere")
        self.assertEqual(services.balance(self.guest), Decimal("87.50"))
        with self.assertRaisesMessage(services.CashError, "Saldo insufficiente"):
            services.add_movement(self.guest, self.operator, "expense", "90", "Scarpe")
        with self.assertRaisesMessage(services.CashError, "futuro"):
            services.add_movement(self.guest, self.operator, "deposit", "5", "Prova",
                                  timezone.localdate() + datetime.timedelta(days=1))
        with self.assertRaises(services.CashError):
            services.add_movement(self.guest, self.operator, "deposit", "0", "Zero")
        self.assertEqual(CashMovement.objects.count(), 2)

    def test_scontrino_cifrato_senza_exif(self):
        services.add_movement(self.guest, self.office, "deposit", "50", "Versamento")
        movement = services.add_movement(self.guest, self.operator, "expense", "8.90", "Crema mani",
                                         receipt=photo())
        self.assertTrue(movement.receipt_storage)
        self.assertEqual(movement.receipt_type, "image/jpeg")
        data = services.read_receipt(movement, self.coordinator)
        self.assertFalse(Image.open(io.BytesIO(data)).getexif())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DOWNLOAD, object_id=str(movement.pk)).exists())
        # il file su disco è cifrato: non contiene l'intestazione JPEG
        from django.core.files.storage import default_storage

        with default_storage.open(movement.receipt_storage) as stored:
            self.assertNotIn(b"\xff\xd8\xff", stored.read()[:16])
        with self.assertRaisesMessage(services.CashError, "non è un'immagine"):
            services.add_movement(self.guest, self.operator, "expense", "1", "Prova",
                                  receipt=SimpleUploadedFile("x.jpg", b"testo", content_type="image/jpeg"))

    def test_annullamento(self):
        deposit = services.add_movement(self.guest, self.office, "deposit", "30", "Versamento")
        expense = services.add_movement(self.guest, self.operator, "expense", "20", "Giornali")
        with self.assertRaisesMessage(services.CashError, "sotto zero"):
            services.void_movement(deposit, self.coordinator, "Errore")
        with self.assertRaises(services.CashError):
            services.void_movement(expense, self.coordinator, " ")
        services.void_movement(expense, self.coordinator, "Registrata due volte")
        self.assertEqual(services.balance(self.guest), Decimal("30"))
        self.assertTrue(CashMovement.objects.filter(pk=expense.pk, voided_at__isnull=False).exists())
        with self.assertRaisesMessage(services.CashError, "già annullato"):
            services.void_movement(expense, self.coordinator, "Ancora")

    def test_rendiconto(self):
        today = timezone.localdate()
        start = today - datetime.timedelta(days=20)
        services.add_movement(self.guest, self.office, "deposit", "40", "Saldo precedente",
                              start - datetime.timedelta(days=5))
        services.add_movement(self.guest, self.office, "deposit", "60", "Versamento", start + datetime.timedelta(days=1))
        services.add_movement(self.guest, self.operator, "expense", "15", "Pedicure", start + datetime.timedelta(days=2))
        data = services.statement(self.guest, start, today)
        self.assertEqual(data["opening"], Decimal("40"))
        self.assertEqual((data["inflow"], data["outflow"], data["closing"]), (Decimal("60"), Decimal("15"), Decimal("85")))
        self.assertEqual(data["lines"][-1][1], Decimal("85"))
        pdf = services.statement_pdf(self.guest, start, today, self.office)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.EXPORT, guest_id=self.guest.pk).exists())

    def test_pagine_ufficio_amministrativo(self):
        self.login(self.office)
        self.assertEqual(self.client.get(reverse("personal:overview")).status_code, 200)
        page = self.client.get(reverse("personal:guest", args=[self.guest.pk]))
        self.assertContains(page, "Piccola cassa")
        self.assertNotContains(page, "Anagrafica e sanitario")  # niente schede cliniche per l'amministrativo
        response = self.client.post(reverse("personal:movement", args=[self.guest.pk]), {
            "kind": "deposit", "amount": "25.00", "occurred_on": timezone.localdate().isoformat(),
            "description": "Versamento del tutore", "counterpart": "Avv. Bianchi"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("personal:movement", args=[self.guest.pk]), {
            "kind": "expense", "amount": "5.00", "occurred_on": timezone.localdate().isoformat(),
            "description": "Francobolli", "receipt": photo()})
        self.assertEqual(response.status_code, 302)
        movement = CashMovement.objects.get(description="Francobolli")
        receipt = self.client.get(reverse("personal:receipt", args=[movement.pk]))
        self.assertEqual(receipt["Content-Type"], "image/jpeg")
        self.assertEqual(receipt["Cache-Control"], "no-store")
        start = timezone.localdate().replace(day=1)
        pdf = self.client.get(reverse("personal:statement", args=[self.guest.pk]),
                              {"start": start.isoformat(), "end": timezone.localdate().isoformat()})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        response = self.client.post(reverse("personal:item", args=[self.guest.pk]), {
            "name": "Orologio da polso", "quantity": "1", "received_on": timezone.localdate().isoformat(),
            "status": "present"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PersonalItem.objects.filter(guest=self.guest, name="Orologio da polso").exists())
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("personal:overview"))

    def test_permessi(self):
        movement = services.add_movement(self.guest, self.office, "deposit", "10", "Versamento")
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("personal:guest", args=[self.guest.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("personal:movement_void", args=[movement.pk])).status_code, 403)
        self.login(self.coordinator)
        response = self.client.post(reverse("personal:movement_void", args=[movement.pk]), {"reason": "Prova"})
        self.assertEqual(response.status_code, 302)
        # l'amministratore di sistema e il medico non gestiscono il denaro degli ospiti
        for user in (self.admin, self.doctor):
            self.login(user)
            self.assertEqual(self.client.get(reverse("personal:overview")).status_code, 403)

    def test_ospite_archiviato(self):
        self.guest.status = "archived"
        self.guest.save()
        with self.assertRaisesMessage(services.CashError, "archiviata"):
            services.add_movement(self.guest, self.office, "deposit", "10", "Versamento")
