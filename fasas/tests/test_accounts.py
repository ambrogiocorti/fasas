from django.contrib.auth.models import Permission
from django.test import override_settings

from fasas.accounts.models import AccessLog, UserPermissionOverride

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
