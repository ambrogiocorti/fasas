"""Custodia delle chiavi: verifica all'avvio e busta di custodia cifrata."""
import io
import tempfile
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import override_settings

from fasas.core import keys

from .base import FasasTestCase

OTHER_KEY = "b3RoZXIta2V5LW5vdC10aGUtcmlnaHQtb25lLTAwMDA="


class KeyCustodyTests(FasasTestCase):
    def test_wrong_key_is_detected(self):
        first = dict((kind, state) for kind, state, _ in keys.check_keys())
        self.assertEqual(first, {"documenti": "ok", "backup": "ok"})
        with override_settings(FASAS_ENCRYPTION_KEYS=[OTHER_KEY]):
            results = {kind: (state, detail) for kind, state, detail in keys.check_keys()}
            self.assertEqual(results["documenti"][0], "error")
            self.assertIn("impronta", results["documenti"][1])
            health = self.client.get("/salute/")
            self.assertEqual(health.status_code, 503)
            with self.assertRaises(CommandError):
                call_command("fasas_chiavi", "verifica", stdout=io.StringIO())
        # rotazione: la nuova chiave in testa e la vecchia in coda aprono ancora i dati
        with override_settings(FASAS_ENCRYPTION_KEYS=[OTHER_KEY] + list(self.settings_keys())):
            self.assertEqual(dict((k, s) for k, s, _ in keys.check_keys())["documenti"], "ok")

    def settings_keys(self):
        from django.conf import settings

        return settings.FASAS_ENCRYPTION_KEYS

    def test_envelope_roundtrip(self):
        folder = Path(tempfile.mkdtemp())
        phrase = folder / "frase.txt"
        phrase.write_text("cassaforte della direzione 2026", encoding="utf-8")
        out = io.StringIO()
        call_command("fasas_chiavi", "busta", str(folder / "busta.fkey"), "--frase-da-file", str(phrase), stdout=out)
        self.assertIn("impronta documenti", out.getvalue())
        data = (folder / "busta.fkey").read_bytes()
        from django.conf import settings

        self.assertNotIn(settings.FASAS_ENCRYPTION_KEYS[0].encode(), data)  # le chiavi sono cifrate
        opened = io.StringIO()
        call_command("fasas_chiavi", "apri", str(folder / "busta.fkey"), "--frase-da-file", str(phrase), stdout=opened)
        self.assertIn(f"FASAS_ENCRYPTION_KEYS={settings.FASAS_ENCRYPTION_KEYS[0]}", opened.getvalue())
        self.assertIn(f"FASAS_BACKUP_KEY={settings.FASAS_BACKUP_KEY}", opened.getvalue())
        phrase.write_text("frase sbagliata ma lunga", encoding="utf-8")
        with self.assertRaises(CommandError):
            call_command("fasas_chiavi", "apri", str(folder / "busta.fkey"), "--frase-da-file", str(phrase),
                         stdout=io.StringIO())
        with self.assertRaises(keys.EnvelopeError):
            keys.make_envelope("corta")
