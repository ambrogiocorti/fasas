import datetime
import time

from django.utils import timezone

from fasas.core.jobs import JOBS, run_job
from fasas.documents.models import Document
from fasas.notifications.models import Notification

from .base import FasasTestCase


class JobTests(FasasTestCase):
    def test_every_job_runs(self):
        for name in JOBS:
            result = run_job(name)
            self.assertIsInstance(result, dict, name)

    def test_document_expiry_notification(self):
        Document.objects.create(guest=self.guest, title="Carta d'identità", category="identity",
                                expires_on=timezone.localdate() + datetime.timedelta(days=5))
        run_job("documents")
        run_job("documents")
        self.assertEqual(Notification.objects.filter(kind="document_expiring", recipient=self.coordinator).count(), 1)

    def test_session_idle_timeout_logs_out(self):
        from fasas.accounts.models import AccessLog

        self.login(self.operator)
        self.assertEqual(self.client.get("/").status_code, 200)
        session = self.client.session
        session["fasas_last_activity"] = int(time.time()) - 3 * 3600
        session.save()
        response = self.client.get("/ospiti/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accesso/entra/", response["Location"])
        self.assertTrue(AccessLog.objects.filter(event="timeout", user=self.operator).exists())
