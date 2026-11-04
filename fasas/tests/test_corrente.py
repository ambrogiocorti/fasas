"""
Gruppo di continuità: quando manca la corrente il FASAS avvisa il personale (una volta per evento) e lo mostra
nel controllo di salute; lo spegnimento ordinato del server lo fa NUT (provato nella CI con un gruppo simulato).
"""
import json
import shutil
import tempfile
from pathlib import Path

from django.test import override_settings
from django.utils import timezone

from fasas.core.jobs import run_job
from fasas.core.monitoring import checks
from fasas.core.power import check_events
from fasas.notifications.models import Notification

from .base import FasasTestCase


class PowerTests(FasasTestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="fasas-ups-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.status = self.folder / "stato.json"
        override = override_settings(FASAS_UPS_STATUS_FILE=str(self.status))
        override.enable()
        self.addCleanup(override.disable)

    def event(self, name):
        self.status.write_text(json.dumps({"evento": name, "quando": timezone.now().isoformat()}))

    def health(self):
        return {name: (level, detail) for name, level, detail in checks()}.get("gruppo_continuita")

    def test_not_configured(self):
        with override_settings(FASAS_UPS_STATUS_FILE=""):
            self.assertEqual(run_job("ups"), {"enabled": False})
            self.assertIsNone(self.health())

    def test_power_loss_warns_the_shift_once(self):
        self.event("ONBATT")
        result = check_events()
        self.assertEqual(result["evento"], "ONBATT")
        alerts = Notification.objects.filter(kind="power", title__startswith="Corrente assente")
        self.assertEqual({n.recipient.username for n in alerts}, {"admin", "coord", "oper"})
        self.assertTrue(all(n.level == "critical" for n in alerts))
        self.assertIn("modalità senza rete", alerts.first().message)
        check_events()
        self.assertEqual(Notification.objects.filter(kind="power").count(), 3)  # nessun doppione
        self.assertEqual(self.health()[0], "warning")
        self.assertIn("a batteria", self.health()[1])

    def test_power_back_and_cable(self):
        self.event("ONLINE")
        check_events()
        self.assertTrue(Notification.objects.filter(kind="power", title="Corrente tornata", level="info").exists())
        self.assertEqual(self.health(), ("ok", "alimentato dalla rete elettrica"))
        self.event("COMMBAD")
        check_events()
        self.assertEqual(self.health()[0], "warning")

    def test_missing_or_broken_file(self):
        self.assertEqual(check_events(), {"enabled": True, "evento": None})
        self.assertEqual(self.health()[0], "warning")
        self.status.write_text("non è json")
        self.assertEqual(check_events()["evento"], None)
