"""Moduli accendibili uno per uno e configurazione per il pilota."""
from django.urls import reverse

from fasas.audit.models import AuditLog
from fasas.core import modules
from fasas.core.jobs import run_job
from fasas.core.models import SystemConfig

from .base import FasasTestCase


def set_off(*keys):
    config = SystemConfig.get()
    config.disabled_modules = list(keys)
    config.save()


class ModulesTests(FasasTestCase):
    def test_all_modules_on_by_default(self):
        self.assertTrue(all(modules.states().values()))

    def test_disabled_module_hides_menu_and_page(self):
        self.login(self.coordinator)
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("appointments:list"))
        set_off("appointments")
        dashboard = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(dashboard, reverse("appointments:list"))
        self.assertNotContains(dashboard, "Visite oggi e domani")
        response = self.client.get(reverse("appointments:list"))
        self.assertContains(response, "funzione spenta", status_code=404)

    def test_stock_off_keeps_drug_catalog(self):
        set_off("stock")
        self.login(self.coordinator)
        self.assertEqual(self.client.get(reverse("pharmacy:stock")).status_code, 404)
        self.assertEqual(self.client.get(reverse("pharmacy:drug_list")).status_code, 200)

    def test_reports_off_keeps_guest_export(self):
        set_off("reports")
        self.assertIsNone(modules.for_view("reports", "guest_export"))
        self.assertEqual(modules.for_view("reports", "list").key, "reports")

    def test_guest_tabs_follow_modules(self):
        self.login(self.coordinator)
        url = reverse("guests:detail", args=[self.guest.pk])
        self.assertContains(self.client.get(url), reverse("pai:guest", args=[self.guest.pk]))
        set_off("pai", "wounds")
        page = self.client.get(url)
        self.assertNotContains(page, reverse("pai:guest", args=[self.guest.pk]))
        self.assertNotContains(page, reverse("wounds:guest", args=[self.guest.pk]))

    def test_job_skipped_when_module_off(self):
        set_off("appointments")
        self.assertIn("spento", run_job("appointments"))

    def test_protocols_off_no_activation(self):
        from fasas.protocols.engine import on_parameter_reading, open_activations

        set_off("protocols")
        self.assertIsNone(on_parameter_reading(object()))  # non legge nemmeno il dato
        self.assertEqual(list(open_activations()), [])

    def test_pilot_configuration_and_all_on(self):
        self.login(self.admin)
        url = reverse("core:modules")
        self.assertContains(self.client.get(url), "Configurazione per il pilota")
        self.client.post(url, {"action": "pilot"})
        self.assertEqual(modules.disabled(), set(modules.PILOT_OFF))
        self.assertIn("staffing", modules.states())
        self.assertTrue(modules.is_on("staffing") and modules.is_on("billing") and modules.is_on("feedback"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.CONFIG).exists())
        self.client.post(url, {"action": "all"})
        self.assertEqual(modules.disabled(), set())

    def test_one_by_one(self):
        self.login(self.admin)
        keep = [m.key for m in modules.MODULES if m.key != "wounds"]
        self.client.post(reverse("core:modules"), {"action": "save", "on": keep})
        self.assertEqual(modules.disabled(), {"wounds"})

    def test_only_admin_manages_modules(self):
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("core:modules")).status_code, 403)
