"""Ogni ruolo vede solo le funzionalità che gli competono (spec. §2)."""
from django.urls import reverse

from fasas.notifications.models import Notification
from fasas.notifications.services import notify

from .base import FasasTestCase


class RoleAccessTests(FasasTestCase):
    def assert_status(self, user, names, status):
        self.login(user)
        for name, args in names:
            url = reverse(name, args=args)
            self.assertEqual(self.client.get(url).status_code, status, f"{user.username} {url}")

    def test_each_role_has_its_own_dashboard(self):
        headings = {self.operator: "Il mio turno", self.coordinator: "Coordinamento",
                    self.doctor: "Area medica", self.admin: "Pannello di sistema"}
        for user, heading in headings.items():
            self.login(user)
            response = self.client.get(reverse("core:dashboard"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"<h1>{heading}")
            for other in set(headings.values()) - {heading}:
                self.assertNotContains(response, f"<h1>{other}")

    def test_operator_daily_work_only(self):
        self.assert_status(self.operator, [
            ("clinical:board", []), ("daily:checklist", []), ("daily:evacuations", []),
            ("guests:detail", [self.guest.pk]), ("protocols:activations", []),
        ], 200)
        self.assert_status(self.operator, [
            ("clinical:therapy_overview", []), ("clinical:therapy_create", [self.guest.pk]),
            ("clinical:sos_pending", []), ("documents:to_sign", []), ("pharmacy:stock", []),
            ("guests:create", []), ("protocols:list", []), ("reports:list", []), ("accounts:user_list", []),
        ], 403)

    def test_coordinator_manages_records_not_system(self):
        self.assert_status(self.coordinator, [
            ("guests:create", []), ("clinical:sos_pending", []), ("pharmacy:stock", []),
            ("protocols:list", []), ("reports:list", []), ("daily:closures", []),
            ("documents:to_sign", []),  # firma con la propria CIE (firma elettronica avanzata)
        ], 200)
        self.assert_status(self.coordinator, [
            ("accounts:user_list", []), ("audit:list", []), ("backups:list", []), ("core:config", []),
            ("signatures:devices", []),
        ], 403)

    def test_doctor_clinical_scope_only(self):
        self.assert_status(self.doctor, [
            ("clinical:therapy_overview", []), ("clinical:therapy_create", [self.guest.pk]),
            ("clinical:sos_pending", []), ("documents:to_sign", []), ("guests:detail", [self.guest.pk]),
        ], 200)
        self.assert_status(self.doctor, [
            ("clinical:board", []), ("daily:checklist", []), ("daily:evacuations", []), ("daily:closures", []),
            ("pharmacy:stock", []), ("guests:create", []), ("reports:list", []), ("accounts:user_list", []),
            ("protocols:list", []),
        ], 403)

    def test_admin_system_only_no_clinical_records(self):
        self.assert_status(self.admin, [
            ("accounts:user_list", []), ("audit:list", []), ("backups:list", []), ("core:config", []),
            ("protocols:list", []), ("notifications:settings", []),
        ], 200)
        self.assert_status(self.admin, [
            ("guests:list", []), ("guests:detail", [self.guest.pk]), ("search:search", []),
            ("clinical:board", []), ("daily:checklist", []), ("pharmacy:stock", []),
        ], 403)

    def test_menu_follows_permissions(self):
        self.login(self.doctor)
        menu = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertIn(reverse("documents:to_sign"), menu)
        self.assertNotIn(reverse("clinical:board"), menu)
        self.assertNotIn(reverse("pharmacy:stock"), menu)
        self.login(self.admin)
        menu = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertIn(reverse("audit:list"), menu)
        self.assertNotIn(reverse("guests:list"), menu)

    def test_notifications_reach_only_authorized_roles(self):
        notify("sos_validation", "SOS da validare", users=[self.operator, self.coordinator, self.doctor, self.admin])
        recipients = set(Notification.objects.filter(kind="sos_validation").values_list("recipient__username",
                                                                                         flat=True))
        self.assertEqual(recipients, {"coord", "doc"})
