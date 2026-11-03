from django.contrib.auth.models import Permission
from django.test import override_settings

from fasas.accounts.models import AccessLog, User, UserPermissionOverride

from .base import PASSWORD, FasasTestCase


class PermissionTests(FasasTestCase):
    def test_role_defaults(self):
        self.assertTrue(self.operator.has_perm("clinical.add_clinicalevent"))
        self.assertFalse(self.operator.has_perm("clinical.delete_clinicalevent"))  # non cancella eventi
        self.assertFalse(self.operator.has_perm("clinical.change_therapy"))  # non modifica terapie
        self.assertTrue(self.doctor.has_perm("clinical.change_therapy"))
        self.assertTrue(self.doctor.has_perm("signatures.sign_document"))
        self.assertTrue(self.coordinator.has_perm("clinical.validate_sos"))
        self.assertTrue(self.admin.has_perm("audit.view_auditlog"))
        self.assertFalse(self.admin.has_perm("clinical.add_therapy"))

    def test_granular_overrides(self):
        perm = Permission.objects.get(codename="add_clinicalevent", content_type__app_label="clinical")
        UserPermissionOverride.objects.create(user=self.operator, permission=perm, allow=False)
        self.operator.clear_permission_cache()
        self.assertFalse(self.operator.has_perm("clinical.add_clinicalevent"))
        extra = Permission.objects.get(codename="delete_clinicalevent")
        UserPermissionOverride.objects.create(user=self.operator, permission=extra, allow=True)
        self.operator.clear_permission_cache()
        self.assertTrue(self.operator.has_perm("clinical.delete_clinicalevent"))

    def test_permission_page_saves_overrides(self):
        self.login(self.admin)
        perm = Permission.objects.get(codename="add_clinicalevent", content_type__app_label="clinical")
        response = self.client.post(f"/utenti/{self.operator.pk}/permessi/", {f"perm_{perm.pk}": "deny"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserPermissionOverride.objects.get(user=self.operator, permission=perm).allow)

    def test_role_change_switches_group(self):
        self.operator.role = "coordinator"
        self.operator.save()
        self.assertEqual(list(self.operator.groups.values_list("name", flat=True)), ["Coordinatore sanitario"])

    def test_pages_restricted_by_role(self):
        self.login(self.operator)
        for url in ["/audit/", "/utenti/", "/backup/", "/configurazione/", "/log-accessi/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.login(self.admin)
        for url in ["/audit/", "/utenti/", "/backup/", "/configurazione/", "/log-accessi/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_login_required(self):
        response = self.client.get("/ospiti/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accesso/entra/", response["Location"])


class AccessLogTests(FasasTestCase):
    @override_settings(FASAS_LOGIN_MAX_FAILURES=3)
    def test_access_log_and_lockout(self):
        for _ in range(3):
            self.client.post("/accesso/entra/", {"username": "oper", "password": "sbagliata"},
                             HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) Chrome/120")
        self.assertEqual(AccessLog.objects.filter(event="failed", username="oper").count(), 3)
        self.assertIn("Windows", AccessLog.objects.first().device)
        response = self.client.post("/accesso/entra/", {"username": "oper", "password": PASSWORD})
        self.assertContains(response, "Troppi tentativi")
        self.assertTrue(AccessLog.objects.filter(event="locked").exists())

    def test_successful_login_logged(self):
        response = self.client.post("/accesso/entra/", {"username": "oper", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        log = AccessLog.objects.get(event="login")
        self.assertEqual(log.user, self.operator)
        self.assertEqual(log.ip_address, "127.0.0.1")

    @override_settings(FASAS_ALLOWED_NETWORKS=["10.0.0.0/8"])
    def test_network_restriction(self):
        from django.http import HttpResponse
        from django.test import RequestFactory

        from fasas.core.middleware import AllowedNetworksMiddleware

        # il middleware legge le reti all'avvio: si verifica con un'istanza nuova
        mw = AllowedNetworksMiddleware(lambda r: HttpResponse("ok"))
        self.assertEqual(mw(RequestFactory().get("/", REMOTE_ADDR="192.168.1.5")).status_code, 403)
        self.assertEqual(mw(RequestFactory().get("/", REMOTE_ADDR="10.1.2.3")).status_code, 200)


class DemoDataGuardTests(FasasTestCase):
    def test_demo_users_refused_outside_test_installations(self):
        import io

        from django.core.management import CommandError, call_command

        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("fasas_demo", "--skip-if-exists", stdout=io.StringIO())
        self.assertFalse(User.objects.filter(username="medico").exists())


class UserManagementScreenTests(FasasTestCase):
    def test_list_create_update_password(self):
        from django.urls import reverse

        self.login(self.admin)
        url = reverse("accounts:user_list")
        self.assertContains(self.client.get(url, {"q": "oper", "role": "operator"}), "Oper")
        create = reverse("accounts:user_create")
        self.assertEqual(self.client.get(create).status_code, 200)
        data = {"username": "nuova", "first_name": "Nadia", "last_name": "Nuova", "fiscal_code": "nvonda90a41f205x",
                "role": "operator", "is_active": "on"}
        self.assertContains(self.client.post(create, {**data, "password1": "Lunga-Password-2026!",
                                                      "password2": "Diversa-Password-2026!"}), "non coincidono")
        self.assertEqual(self.client.post(create, {**data, "password1": "123", "password2": "123"}).status_code, 200)
        self.assertFalse(User.objects.filter(username="nuova").exists())  # password troppo debole
        self.client.post(create, {**data, "password1": "Lunga-Password-2026!", "password2": "Lunga-Password-2026!"})
        user = User.objects.get(username="nuova")
        self.assertEqual(user.fiscal_code, "NVONDA90A41F205X")
        self.assertTrue(user.check_password("Lunga-Password-2026!"))
        update = reverse("accounts:user_update", args=[user.pk])
        self.assertEqual(self.client.get(update).status_code, 200)
        self.client.post(update, {**data, "role": "coordinator", "is_active": "on"})
        user.refresh_from_db()
        self.assertEqual(user.role, "coordinator")
        own = reverse("accounts:user_update", args=[self.admin.pk])
        response = self.client.post(own, {"username": "admin", "first_name": "Admin", "last_name": "Test",
                                          "role": "admin"})
        self.assertContains(response, "Non puoi disattivare il tuo stesso utente")
        password = reverse("accounts:user_set_password", args=[user.pk])
        self.assertEqual(self.client.get(password).status_code, 200)
        self.client.post(password, {"new_password1": "Altra-Password-2026!", "new_password2": "Altra-Password-2026!"})
        user.refresh_from_db()
        self.assertTrue(user.check_password("Altra-Password-2026!"))
        self.login(self.operator)
        self.assertRedirects(self.client.get(password), reverse("core:dashboard"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("accounts:user_permissions", args=[user.pk])),
                             reverse("core:dashboard"), fetch_redirect_response=False)

    def test_permission_page_allow_and_back_to_role(self):
        from django.urls import reverse

        self.login(self.admin)
        url = reverse("accounts:user_permissions", args=[self.operator.pk])
        self.assertContains(self.client.get(url), "Eventi")
        perm = Permission.objects.get(codename="delete_clinicalevent")
        self.client.post(url, {f"perm_{perm.pk}": "deny"})
        self.client.post(url, {f"perm_{perm.pk}": "allow"})
        self.assertTrue(UserPermissionOverride.objects.get(user=self.operator, permission=perm).allow)
        self.client.post(url, {})
        self.assertFalse(UserPermissionOverride.objects.filter(user=self.operator).exists())

    def test_access_log_filters_profile_theme_password(self):
        from django.urls import reverse

        AccessLog.objects.create(username="oper", event="login_failed", ip_address="10.0.0.5")
        self.login(self.admin)
        url = reverse("accounts:access_log")
        self.assertContains(self.client.get(url, {"username": "oper", "event": "login_failed", "ip": "10.0",
                                                  "date_from": "2000-01-01", "date_to": "2999-01-01"}), "10.0.0.5")
        self.login(self.operator)
        profile = reverse("accounts:profile")
        self.assertEqual(self.client.get(profile).status_code, 200)
        self.client.post(profile, {"first_name": "Olga", "last_name": "Test", "email": "", "phone": "", "theme": "dark"})
        self.operator.refresh_from_db()
        self.assertEqual((self.operator.first_name, self.operator.theme), ("Olga", "dark"))
        response = self.client.post(reverse("accounts:set_theme"), {"theme": "light", "next": "https://altro.example/"})
        self.assertRedirects(response, reverse("core:dashboard"), fetch_redirect_response=False)
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.theme, "light")
        response = self.client.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD, "new_password1": "Nuova-Password-2026!", "new_password2": "Nuova-Password-2026!"})
        self.assertRedirects(response, profile, fetch_redirect_response=False)
