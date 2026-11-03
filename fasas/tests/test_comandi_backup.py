"""
Comandi da riga di comando per backup, verifica e ripristino (quelli della guida di installazione e del
ripristino d'emergenza): conferma obbligatoria, file mancante o alterato, ripristino completo.
"""
import io

from django.core.management import CommandError, call_command
from django.db import connection

from fasas.audit.services import verify_chain
from fasas.backups.models import BackupRecord
from fasas.guests.models import Guest

from .base import FasasTestCase


class BackupCommandTests(FasasTestCase):
    def run_command(self, *args):
        out = io.StringIO()
        call_command(*args, stdout=out)
        return out.getvalue()

    def test_create_and_verify(self):
        output = self.run_command("backup_create", "--no-media")
        self.assertIn("verifica=OK", output)
        record = BackupRecord.objects.get()
        self.assertEqual(record.kind, BackupRecord.Kind.MANUAL)
        self.assertIn("integrità verificata", self.run_command("backup_verify"))
        self.assertIn("integrità verificata", self.run_command("backup_verify", str(record.pk)))
        with self.assertRaisesMessage(CommandError, "Nessun backup"):
            self.run_command("backup_verify", "9999")
        with open(record.path, "r+b") as handle:
            handle.seek(150)
            byte = handle.read(1)
            handle.seek(150)
            handle.write(bytes([byte[0] ^ 1]))
        with self.assertRaises(CommandError):
            self.run_command("backup_verify")

    def test_restore_refuses_without_confirm_missing_or_tampered_file(self):
        self.run_command("backup_create", "--no-media")
        record = BackupRecord.objects.get()
        with self.assertRaisesMessage(CommandError, "--confirm"):
            self.run_command("backup_restore", str(record.path))
        with self.assertRaisesMessage(CommandError, "non trovato"):
            self.run_command("backup_restore", "inesistente.fbk", "--confirm")
        with open(record.path, "r+b") as handle:
            handle.seek(150)
            byte = handle.read(1)
            handle.seek(150)
            handle.write(bytes([byte[0] ^ 1]))
        with self.assertRaises(CommandError):
            self.run_command("backup_restore", record.filename, "--confirm", "--no-media")

    def test_restore_brings_data_back(self):
        if connection.vendor == "postgresql":
            self.skipTest("su PostgreSQL il ripristino usa pg_restore su un database fermo: provato dal comando "
                          "backup_prova_ripristino su un database separato")
        self.guest.room = "5A"
        self.guest.save()
        self.run_command("backup_create", "--no-media")
        record = BackupRecord.objects.get()
        Guest.objects.filter(pk=self.guest.pk).update(room="99Z")
        output = self.run_command("backup_restore", record.filename, "--confirm", "--no-media")
        self.assertIn("Ripristino completato", output)
        self.assertEqual(Guest.objects.get(pk=self.guest.pk).room, "5A")
        ok, _count, broken = verify_chain()
        self.assertTrue(ok, broken)


class BackupPageTests(FasasTestCase):
    def test_admin_page_run_verify_download(self):
        from django.urls import reverse

        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("backups:list")).status_code, 200)
        response = self.client.post(reverse("backups:run"))
        self.assertRedirects(response, reverse("backups:list"), fetch_redirect_response=False)
        record = BackupRecord.objects.get()
        self.assertTrue(record.verify_ok)
        self.client.post(reverse("backups:verify", args=[record.pk]))
        download = self.client.get(reverse("backups:download", args=[record.pk]))
        self.assertIn("attachment", download["Content-Disposition"])
        content = b"".join(download.streaming_content)
        self.assertNotIn(b"RSSMRA80A01F205X", content)  # il file scaricato resta cifrato
        record.path.unlink()
        self.assertEqual(self.client.get(reverse("backups:download", args=[record.pk])).status_code, 404)
        self.client.post(reverse("backups:verify", args=[record.pk]))
        record.refresh_from_db()
        self.assertFalse(record.verify_ok)

    def test_only_admin(self):
        from django.urls import reverse

        for user in (self.coordinator, self.operator, self.doctor):
            self.login(user)
            self.assertEqual(self.client.get(reverse("backups:list")).status_code, 403, user.username)
