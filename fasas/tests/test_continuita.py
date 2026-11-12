"""
Disco di continuità: copia cifrata ogni 5 minuti su un disco esterno sempre collegato, avviso se il disco manca,
conservazione delle copie, ripristino dell'ultima copia.
"""
import datetime
import io
import json
import shutil
import tempfile
from pathlib import Path

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from fasas.backups import continuity
from fasas.core.jobs import run_job
from fasas.core.monitoring import checks
from fasas.guests.models import Guest
from fasas.notifications.models import Notification

from .base import FasasTestCase


class ContinuityTests(FasasTestCase):
    def setUp(self):
        self.disk = Path(tempfile.mkdtemp(prefix="fasas-disco-continuita-"))
        self.addCleanup(shutil.rmtree, self.disk, ignore_errors=True)
        override = override_settings(FASAS_CONTINUITY_DIR=str(self.disk))
        override.enable()
        self.addCleanup(override.disable)

    def prepare_disk(self):
        (self.disk / continuity.MARKER).write_text("FASAS")

    def test_not_configured_does_nothing(self):
        with override_settings(FASAS_CONTINUITY_DIR=""):
            self.assertEqual(continuity.continuous_copy(), {"enabled": False})
            self.assertEqual(run_job("continuity"), {"enabled": False})
            self.assertNotIn("copia_continua", [name for name, _, _ in checks()])

    def test_disk_not_connected_stops_and_alerts(self):
        with self.assertRaisesMessage(continuity.ContinuityError, "non collegato"):
            continuity.continuous_copy()
        self.assertEqual(list(self.disk.iterdir()), [])  # non scrive nulla sul disco interno
        alert = Notification.objects.get(recipient=self.admin, title="Copia continua NON riuscita")
        self.assertEqual(alert.level, "critical")
        state = {name: (level, detail) for name, level, detail in checks()}
        self.assertEqual(state["copia_continua"][0], "warning")
        self.assertIn("non collegato", state["copia_continua"][1])

    def test_copy_database_and_files(self):
        from fasas.documents.services import create_document

        self.prepare_disk()
        create_document(self.guest, "consent", "Consenso", user=self.coordinator, data=b"%PDF-1.4 prova",
                        filename="consenso.pdf")
        result = continuity.continuous_copy()
        self.assertTrue(result["enabled"])
        self.assertEqual(result["media_copied"], 1)
        copy = self.disk / "database" / result["file"]
        self.assertTrue(copy.exists())
        self.assertNotIn(b"RSSMRA80A01F205X", copy.read_bytes())  # cifrata
        self.assertEqual(len(list((self.disk / "media").rglob("*.enc"))), 1)
        status = json.loads((self.disk / continuity.STATUS).read_text())
        self.assertEqual(status["file"], result["file"])
        self.assertIsNotNone(continuity.last_copy())
        state = {name: level for name, level, _ in checks()}
        self.assertEqual(state["copia_continua"], "ok")
        later = continuity.continuous_copy(now=timezone.now() + datetime.timedelta(minutes=5))
        self.assertEqual(later["media_copied"], 0)  # solo i file nuovi o cambiati
        self.assertEqual(len(continuity.copies()), 2)

    def test_retention(self):
        self.prepare_disk()
        folder = self.disk / "database"
        folder.mkdir()
        now = timezone.now()
        moments = [now - datetime.timedelta(minutes=5 * i) for i in range(0, 12)]  # ultima ora: tutte
        old = timezone.localtime(now - datetime.timedelta(days=2)).replace(minute=40, second=0, microsecond=0)
        moments += [old - datetime.timedelta(minutes=5 * i) for i in range(0, 6)]  # stessa ora di due giorni fa: una
        moments += [now - datetime.timedelta(days=10)]  # oltre 7 giorni: nessuna
        for moment in moments:
            (folder / f"{continuity.PREFIX}{continuity._stamp(moment)}.fbk").write_bytes(b"x")
        removed = continuity._prune(folder, now)
        left = continuity.copies()
        self.assertEqual(len(left), 12 + 1)
        self.assertEqual(removed, len(moments) - 13)

    def test_restore_latest(self):
        if connection.vendor == "postgresql":
            self.skipTest("su PostgreSQL il ripristino usa pg_restore su un database fermo")
        self.prepare_disk()
        self.guest.room = "3B"
        self.guest.save()
        continuity.continuous_copy()
        Guest.objects.filter(pk=self.guest.pk).update(room="99Z")
        out = io.StringIO()
        call_command("fasas_ripristina_continuita", "--confirm", "--no-media", stdout=out)
        self.assertIn("Ripristino completato", out.getvalue())
        self.assertEqual(Guest.objects.get(pk=self.guest.pk).room, "3B")

    def test_restore_command_checks(self):
        with self.assertRaisesMessage(CommandError, "non collegato"):
            call_command("fasas_ripristina_continuita", "--elenca", stdout=io.StringIO())
        self.prepare_disk()
        with self.assertRaisesMessage(CommandError, "Nessuna copia"):
            call_command("fasas_ripristina_continuita", "--confirm", stdout=io.StringIO())
        continuity.continuous_copy()
        out = io.StringIO()
        call_command("fasas_ripristina_continuita", "--elenca", stdout=out)
        self.assertIn(continuity.PREFIX, out.getvalue())
        with self.assertRaisesMessage(CommandError, "--confirm"):
            call_command("fasas_ripristina_continuita", stdout=io.StringIO())
        other = Path(tempfile.mkdtemp(prefix="fasas-altro-"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        with self.assertRaisesMessage(CommandError, "non c'è un disco di continuità"):
            call_command("fasas_ripristina_continuita", "--cartella", str(other), "--confirm", stdout=io.StringIO())
