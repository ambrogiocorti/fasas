from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from fasas.audit.models import AuditLog
from fasas.clinical.models import ParameterType, TherapyAdministration

from .base import FasasTestCase


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
            "therapy": therapy.pk, "scheduled_date": "2026-01-01", "scheduled_time": "08:00", "status": "given"})
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
