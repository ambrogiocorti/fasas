"""Backup fuori sede su object storage S3 con blocco delle modifiche e prova di ripristino con verbale."""
import datetime
import io
from unittest import mock

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.backups import offsite
from fasas.backups.models import BackupRecord, RestoreTest
from fasas.backups.restore_test import run_restore_test
from fasas.backups.services import create_backup, scheduled_backup, verify_backup
from fasas.notifications.models import Notification

from .base import FasasTestCase

try:
    from moto import mock_aws
except ImportError:  # pragma: no cover
    mock_aws = None

OFFSITE = {"FASAS_OFFSITE_BUCKET": "fasas-prova", "FASAS_OFFSITE_ACCESS_KEY": "prova",
           "FASAS_OFFSITE_SECRET_KEY": "prova", "FASAS_OFFSITE_REGION": "eu-south-1", "FASAS_OFFSITE_ENDPOINT": ""}


def make_bucket():
    s3 = offsite.client()
    s3.create_bucket(Bucket="fasas-prova", CreateBucketConfiguration={"LocationConstraint": "eu-south-1"},
                     ObjectLockEnabledForBucket=True)
    return s3


@override_settings(**OFFSITE)
class OffsiteBackupTests(FasasTestCase):
    def setUp(self):
        if mock_aws is None:
            self.skipTest("moto non installato")
        self.aws = mock_aws()
        self.aws.start()
        self.addCleanup(self.aws.stop)
        self.s3 = make_bucket()

    def test_nightly_backup_is_copied_and_locked(self):
        result = scheduled_backup()
        self.assertTrue(result["offsite"], result)
        record = BackupRecord.objects.get()
        self.assertTrue(record.offsite_key.startswith("fasas/backup/fasas-backup-"))
        self.assertGreater(record.offsite_locked_until, timezone.now() + datetime.timedelta(days=29))
        head = self.s3.head_object(Bucket="fasas-prova", Key=record.offsite_key)
        self.assertEqual(head["Metadata"]["sha256"], record.sha256)
        self.assertEqual(head["ObjectLockMode"], "COMPLIANCE")
        self.assertEqual(head["ContentLength"], record.size)
        keys = [o["Key"] for o in self.s3.list_objects_v2(Bucket="fasas-prova")["Contents"]]
        self.assertTrue(any(k.startswith("fasas/audit/punti-di-controllo-") for k in keys))
        # Nemmeno con le credenziali si cancella la versione bloccata (ransomware, errore umano)
        version = self.s3.list_object_versions(Bucket="fasas-prova", Prefix=record.offsite_key)["Versions"][0]
        from botocore.exceptions import ClientError

        with self.assertRaises(ClientError):
            self.s3.delete_object(Bucket="fasas-prova", Key=record.offsite_key, VersionId=version["VersionId"])
        self.assertTrue(AuditLog.objects.filter(action="backup", changes__icontains="copia_fuori_sede").exists())

    def test_upload_failure_alerts_admin_and_keeps_local_backup(self):
        record = create_backup()
        verify_backup(record)
        with override_settings(FASAS_OFFSITE_BUCKET="bucket-inesistente"):
            from fasas.backups.services import copy_offsite

            self.assertFalse(copy_offsite(record))
        record.refresh_from_db()
        self.assertIn("NoSuchBucket", record.offsite_error)
        self.assertTrue(record.path.exists())
        self.assertTrue(Notification.objects.filter(title__contains="fuori sede", recipient=self.admin).exists())

    def test_retention_keeps_daily_and_monthly(self):
        now = timezone.make_aware(datetime.datetime(2026, 10, 30, 3, 0))
        items = [{"key": f"k{i}", "modified": now - datetime.timedelta(days=i, hours=h)}
                 for i in range(0, 400) for h in (0, 1)]
        with override_settings(FASAS_OFFSITE_KEEP_DAILY=30, FASAS_OFFSITE_KEEP_MONTHLY=12):
            keep = offsite.retention_plan(items, now=now)
        self.assertEqual(len([k for k in keep if int(k[1:]) < 30]), 30)  # uno per ciascuno degli ultimi 30 giorni
        self.assertLessEqual(len(keep), 30 + 12)
        self.assertNotIn("k399", keep)

    def test_prune_respects_the_lock(self):
        with override_settings(FASAS_OFFSITE_KEEP_DAILY=1, FASAS_OFFSITE_KEEP_MONTHLY=0):
            for _ in range(2):
                record = create_backup(include_media=False)
                verify_backup(record)
                from fasas.backups.services import copy_offsite

                copy_offsite(record)
            result = offsite.prune()
        self.assertEqual(result["still_locked"], 1)  # il più vecchio è da togliere ma è ancora bloccato
        self.assertEqual(len(offsite.list_backups()), 2)

    def test_restore_test_from_offsite_copy(self):
        if connection.vendor == "postgresql":
            self.skipTest("su PostgreSQL serve FASAS_RESTORE_TEST_DATABASE_URL (prova separata)")
        self.guest.allergies.create(substance="penicillina", severity="severe")
        scheduled_backup()
        with mock.patch("fasas.backups.restore_test.BackupRecord.objects") as local:
            test = run_restore_test(self.admin)
            local.filter.assert_not_called()  # preso dalla copia fuori sede, non dal server
        self.assertEqual(test.result, RestoreTest.Result.OK, test.steps)
        self.assertEqual(test.source, "fuori sede")
        self.assertEqual(test.counts["guests_guest"], 1)
        self.assertGreaterEqual(test.counts["audit_auditlog"], 1)
        self.assertTrue(any("Audit log integro" in step for step in test.steps), test.steps)


class RestoreTestTests(FasasTestCase):
    def test_local_restore_test_and_verbale(self):
        if connection.vendor == "postgresql":
            self.skipTest("su PostgreSQL serve FASAS_RESTORE_TEST_DATABASE_URL")
        create_backup(user=self.admin)
        self.login(self.admin)
        response = self.client.post(reverse("backups:restore_test_run"), follow=True)
        self.assertContains(response, "Verbale della prova di ripristino")
        self.assertContains(response, "Riuscita")
        self.assertContains(response, "audit_auditlog")
        test = RestoreTest.objects.get()
        self.assertEqual(test.source, "locale")
        page = self.client.get(reverse("backups:list"))
        self.assertContains(page, "Prove di ripristino")
        self.assertContains(page, "Nessuna copia fuori sede")
        self.assertTrue(AuditLog.objects.filter(action="restore").exists())

    def test_failure_is_reported(self):
        out = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("backup_prova_ripristino", stdout=out)  # nessun backup
        self.assertEqual(RestoreTest.objects.get().result, RestoreTest.Result.FAILED)
        self.assertTrue(Notification.objects.filter(title__contains="ripristino", recipient=self.admin).exists())

    def test_corrupted_backup_fails_the_test(self):
        record = create_backup()
        with open(record.path, "r+b") as handle:
            handle.seek(300)
            byte = handle.read(1)
            handle.seek(300)
            handle.write(bytes([byte[0] ^ 1]))
        test = run_restore_test()
        self.assertEqual(test.result, RestoreTest.Result.FAILED)
        self.assertIn("impronta", test.steps[-1])
