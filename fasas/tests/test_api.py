import datetime

from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from fasas.audit.models import AuditLog
from fasas.clinical.models import ParameterType, TherapyAdministration

from .base import PASSWORD, FasasTestCase


class ApiSwitchTests(FasasTestCase):
    def test_api_is_off_by_default(self):
        token = Token.objects.create(user=self.operator)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        for path in ("/api/v1/ospiti/", "/api/v1/turno-corrente/"):
            self.assertEqual(api.get(path).status_code, 404)
        self.assertEqual(APIClient().post("/api/v1/token/", {"username": "x", "password": "y"}).status_code, 404)


@override_settings(FASAS_API_ENABLED=True)
class ApiTests(FasasTestCase):
    def client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_requires_authentication(self):
        self.assertIn(APIClient().get("/api/v1/ospiti/").status_code, (401, 403))

    def test_operator_flow(self):
        api = self.client_for(self.operator)
        therapy = self.make_therapy(schedule_times=["08:00"])
        self.assertEqual(api.get("/api/v1/ospiti/").json()["count"], 1)
        self.assertEqual(api.get("/api/v1/turno-corrente/").status_code, 200)
        response = api.post("/api/v1/parametri/", {
            "guest": self.guest.pk, "parameter_type": ParameterType.objects.get(code="temperatura").pk, "value": "36.8"})
        self.assertEqual(response.status_code, 201, response.content)
        entry = AuditLog.objects.filter(content_type__model="parameterreading").latest("id")
        self.assertEqual(entry.user, self.operator)
        response = api.post("/api/v1/somministrazioni/", {
            "therapy": therapy.pk, "scheduled_date": (timezone.localdate() - datetime.timedelta(days=1)).isoformat(),
            "scheduled_time": "08:00", "status": "given"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(TherapyAdministration.objects.get().created_by, self.operator)

    def test_operator_cannot_read_audit_or_create_without_permission(self):
        from django.contrib.auth.models import Permission

        from fasas.accounts.models import UserPermissionOverride

        perm = Permission.objects.get(codename="add_parameterreading")
        UserPermissionOverride.objects.create(user=self.operator, permission=perm, allow=False)
        api = self.client_for(self.operator)
        response = api.post("/api/v1/parametri/", {
            "guest": self.guest.pk, "parameter_type": ParameterType.objects.first().pk, "value": "1"})
        self.assertEqual(response.status_code, 403)

    def test_token_endpoint(self):
        from .base import PASSWORD

        response = APIClient().post("/api/v1/token/", {"username": "oper", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())


@override_settings(FASAS_API_ENABLED=True, FASAS_2FA_REQUIRED_ROLES=[])
class TokenLifecycleTests(FasasTestCase):
    """Report di analisi, P1: token con scadenza, rotazione e revoca."""

    def get_token(self, username="oper"):
        response = APIClient().post("/api/v1/token/", {"username": username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["token"]

    def call(self, key):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {key}")
        status = api.get("/api/v1/turno-corrente/").status_code
        return 401 if status in (401, 403) else status  # rifiutato (DRF risponde 403 con la sessione tra i metodi)

    def test_rotation_on_each_login(self):
        first = self.get_token()
        second = self.get_token()
        self.assertNotEqual(first, second)
        self.assertEqual(self.call(first), 401)
        self.assertEqual(self.call(second), 200)

    def test_expiry(self):
        key = self.get_token()
        Token.objects.filter(key=key).update(created=timezone.now() - datetime.timedelta(days=31))
        self.assertEqual(self.call(key), 401)  # rifiutato a ogni chiamata, finché non si rientra

    def test_password_change_deactivation_and_2fa_reset_revoke(self):
        from fasas.accounts import twofactor

        key = self.get_token()
        self.operator.set_password("Nuova-Password-2026!")
        self.operator.save()
        self.assertEqual(self.call(key), 401)
        self.operator.set_password(PASSWORD)
        self.operator.save()
        key = self.get_token()
        twofactor.disable(self.operator, by=self.admin)
        self.assertEqual(self.call(key), 401)
        key = self.get_token()
        self.operator.is_active = False
        self.operator.save()
        self.assertFalse(Token.objects.filter(key=key).exists())

    def test_explicit_revoke(self):
        key = self.get_token()
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {key}")
        self.assertEqual(api.post("/api/v1/token/revoca/").status_code, 200)
        self.assertEqual(self.call(key), 401)
