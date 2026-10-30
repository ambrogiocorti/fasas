"""Monitoraggio: controllo di salute, job periodici, registro errori senza dati sanitari."""
from unittest import mock

from django.http import HttpResponse
from django.test import override_settings
from django.urls import include, path, reverse

from fasas.core.jobs import run_job
from fasas.core.models import ErrorEvent, JobRun
from fasas.notifications.models import Notification

from .base import FasasTestCase


def broken_view(request, pk):
    raise ValueError(f"Errore sulla cartella di Mario Rossi, diagnosi epilessia (ospite {pk})")


def fine_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("guasto/<int:pk>/", broken_view),
    path("", include("config.urls")),
]


class HealthTests(FasasTestCase):
    def test_public_status_without_details(self):
        response = self.client.get("/salute/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "degraded")  # nessun backup né verifica audit ancora
        self.assertNotIn("checks", body)
        self.assertIn("version", body)

    @override_settings(FASAS_HEALTH_TOKEN="segreto-di-monitoraggio")
    def test_details_with_token(self):
        self.assertNotIn("checks", self.client.get("/salute/?token=sbagliato").json())
        checks = self.client.get("/salute/", HTTP_AUTHORIZATION="Bearer segreto-di-monitoraggio").json()["checks"]
        self.assertEqual(checks["database"]["status"], "ok")
        self.assertEqual(checks["backup"]["status"], "warning")
        self.assertIn("backup", checks["job"]["detail"])
        self.assertNotIn("restore_test", checks["job"]["detail"])  # trimestrale: non ancora dovuta
        for job in ("close_shifts", "protocols", "appointments", "stock", "documents", "pai_reviews", "reports",
                    "report_retention", "backup", "audit_verify", "imports_cleanup", "cie_cleanup"):
            run_job(job)
        checks = self.client.get("/salute/?token=segreto-di-monitoraggio").json()["checks"]
        self.assertEqual(checks["job"]["status"], "ok", checks["job"])
        self.assertEqual(checks["backup"]["status"], "ok")
        self.assertEqual(checks["audit"]["status"], "ok")

    def test_database_down_is_503(self):
        with mock.patch("fasas.core.monitoring.ping_database", return_value=False):
            response = self.client.get("/salute/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")


@override_settings(ROOT_URLCONF=__name__)
class ErrorRecordingTests(FasasTestCase):
    def test_errors_recorded_without_health_data(self):
        self.client.raise_request_exception = False
        self.login(self.operator)
        self.assertEqual(self.client.get("/guasto/42/").status_code, 500)
        self.assertEqual(self.client.get("/guasto/43/").status_code, 500)
        event = ErrorEvent.objects.get()
        self.assertEqual((event.where, event.exception, event.count), ("GET guasto/<int:pk>/", "ValueError", 2))
        self.assertIn("fasas/tests/test_monitoring.py", event.frames)
        stored = " ".join([event.where, event.exception, event.template, event.frames])
        for secret in ("Rossi", "epilessia", "42", "43"):
            self.assertNotIn(secret, stored)
        notification = Notification.objects.get(kind="system_error", recipient=self.admin)
        self.assertNotIn("Rossi", notification.message)
        self.assertFalse(Notification.objects.filter(kind="system_error", recipient=self.operator).exists())

        self.login(self.admin)
        page = self.client.get(reverse("core:errors"))
        self.assertContains(page, "ValueError")
        self.assertNotContains(page, "Rossi")
        self.client.post(reverse("core:errors"), {"pk": event.pk})
        event.refresh_from_db()
        self.assertIsNotNone(event.resolved_at)
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("core:errors")).status_code, 403)


class JobHeartbeatTests(FasasTestCase):
    def test_job_runs_and_failures_are_tracked(self):
        run_job("stock")
        run = JobRun.objects.get(name="stock")
        self.assertTrue(run.last_ok)
        self.assertEqual(run.runs, 1)

        def failing():
            raise RuntimeError("magazzino di Mario Rossi non raggiungibile")

        with mock.patch("fasas.core.jobs.import_string", return_value=failing), self.assertRaises(RuntimeError):
            run_job("stock")
        run.refresh_from_db()
        self.assertFalse(run.last_ok)
        self.assertEqual(run.runs, 2)
        self.assertTrue(run.last_error.startswith("RuntimeError in fasas/tests/test_monitoring.py"))
        self.assertNotIn("Rossi", run.last_error)
        self.assertTrue(ErrorEvent.objects.filter(exception="RuntimeError").exists())
