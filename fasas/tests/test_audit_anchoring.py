"""Punti di controllo dell'audit: verifica salvata, marca temporale RFC 3161, storia riscritta rilevata."""
import datetime
import io
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse

from fasas.audit import anchoring
from fasas.audit.models import AuditCheckpoint, AuditLog, ImmutableRecordError
from fasas.audit.services import log_event, verify_chain
from fasas.notifications.models import Notification

from .base import FasasTestCase


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SOLO PROVA")])


def make_test_tsa(folder):
    """CA e TSA di prova SOLO per i test (in produzione serve la TSA reale di un prestatore)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = (x509.CertificateBuilder().subject_name(_name("CA di prova")).issuer_name(_name("CA di prova"))
          .public_key(ca_key.public_key()).serial_number(1).not_valid_before(now - datetime.timedelta(days=1))
          .not_valid_after(now + datetime.timedelta(days=30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    tsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tsa = (x509.CertificateBuilder().subject_name(_name("TSA di prova")).issuer_name(ca.subject)
           .public_key(tsa_key.public_key()).serial_number(2).not_valid_before(now - datetime.timedelta(days=1))
           .not_valid_after(now + datetime.timedelta(days=30))
           .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
           .add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
           .sign(ca_key, hashes.SHA256()))
    pem = folder / "tsa-ca.pem"
    pem.write_bytes(ca.public_bytes(serialization.Encoding.PEM) + tsa.public_bytes(serialization.Encoding.PEM))
    (folder / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    from pyhanko.sign.timestamps import DummyTimeStamper
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    tsa_asn1 = asn1_x509.Certificate.load(tsa.public_bytes(serialization.Encoding.DER))
    key_asn1 = asn1_keys.PrivateKeyInfo.load(tsa_key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    store = SimpleCertificateStore.from_certs([tsa_asn1])
    return DummyTimeStamper(tsa_cert=tsa_asn1, tsa_key=key_asn1, certs_to_embed=store)


class AnchoringTests(FasasTestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        for i in range(3):
            log_event(AuditLog.Action.SYSTEM, repr_text=f"evento {i}", user=self.admin)

    def stamped(self):
        return mock.patch.object(anchoring, "timestamper", return_value=make_test_tsa(self.folder))

    def test_without_tsa_checkpoint_is_declared_unstamped(self):
        checkpoint = anchoring.create_checkpoint()
        self.assertTrue(checkpoint.chain_ok)
        self.assertFalse(checkpoint.timestamped)
        self.assertEqual(checkpoint.head_hash, AuditLog.objects.order_by("-id").first().hash)
        with zipfile.ZipFile(io.BytesIO(anchoring.receipt_zip(checkpoint))) as archive:
            self.assertNotIn("marca-temporale.tst", archive.namelist())
            self.assertIn("NON ha marca temporale", archive.read("LEGGIMI.txt").decode())
        with self.assertRaises(ImmutableRecordError):
            checkpoint.save()
        with self.assertRaises(ImmutableRecordError):
            AuditCheckpoint.objects.all().delete()

    def test_timestamped_checkpoint_verifiable_by_third_parties(self):
        with self.stamped():
            checkpoint = anchoring.create_checkpoint()
        self.assertTrue(checkpoint.timestamped)
        self.assertIsNotNone(checkpoint.timestamp_time)
        result = anchoring.verify_timestamp(checkpoint.timestamp_token, checkpoint.message())
        self.assertTrue(result["intact"])
        self.assertFalse(result["trusted"])  # senza CA configurate non si dichiara affidabile
        with override_settings(FASAS_SIGNATURE_TRUST_ROOTS=str(self.folder / "ca.pem")):
            self.assertTrue(anchoring.verify_timestamp(checkpoint.timestamp_token, checkpoint.message())["trusted"])
        other = anchoring.anchor_message(checkpoint.last_entry_id, "0" * 64, checkpoint.entries)
        self.assertFalse(anchoring.verify_timestamp(checkpoint.timestamp_token, other)["intact"])

        with zipfile.ZipFile(io.BytesIO(anchoring.receipt_zip(checkpoint))) as archive:
            archive.extractall(self.folder / "ricevuta")
        if shutil.which("openssl") is None:  # pragma: no cover
            raise unittest.SkipTest("openssl non disponibile")
        verify = subprocess.run(
            ["openssl", "ts", "-verify", "-data", "punto-di-controllo.txt", "-in", "marca-temporale.tst", "-token_in",
             "-CAfile", str(self.folder / "tsa-ca.pem")],
            cwd=self.folder / "ricevuta", capture_output=True, text=True)
        self.assertIn("Verification: OK", verify.stdout + verify.stderr)

    def test_rewritten_history_is_detected(self):
        anchoring.create_checkpoint()
        log_event(AuditLog.Action.SYSTEM, repr_text="dopo il punto di controllo", user=self.admin)
        if connection.vendor == "postgresql":
            return  # il database rifiuta già qualsiasi UPDATE sull'audit (test_audit)
        # Chi controlla il database altera una voce e ricalcola TUTTA la catena: la catena torna coerente…
        entries = list(AuditLog.objects.order_by("id"))
        entries[1].reason = "alterato"
        previous = ""
        with connection.cursor() as cursor:
            for entry in entries:
                entry.prev_hash = previous
                entry.hash = entry.compute_hash()
                cursor.execute("UPDATE audit_auditlog SET reason=%s, prev_hash=%s, hash=%s WHERE id=%s",
                               [entry.reason, entry.prev_hash, entry.hash, entry.pk])
                previous = entry.hash
        self.assertTrue(verify_chain()[0])
        # …ma l'impronta della voce già ancorata è cambiata
        checkpoint = anchoring.create_checkpoint()
        self.assertFalse(checkpoint.chain_ok)
        self.assertEqual(len(checkpoint.mismatched_checkpoints), 1)
        self.assertTrue(Notification.objects.filter(kind="audit_chain_broken", recipient=self.admin).exists())
        with self.assertRaises(CommandError):
            call_command("audit_verify", stdout=io.StringIO())

    def test_tsa_failure_is_recorded_not_faked(self):
        failing = mock.Mock()
        failing.async_timestamp = mock.AsyncMock(side_effect=OSError("TSA non raggiungibile"))
        with mock.patch.object(anchoring, "timestamper", return_value=failing):
            checkpoint = anchoring.create_checkpoint()
        self.assertTrue(checkpoint.chain_ok)
        self.assertFalse(checkpoint.timestamped)
        self.assertIn("TSA non raggiungibile", checkpoint.timestamp_error)

    def test_command_and_pages(self):
        with self.stamped():
            out = io.StringIO()
            call_command("audit_verify", "--salva", stdout=out)
        self.assertIn("1 con marca temporale integra", out.getvalue())
        self.login(self.admin)
        with mock.patch("fasas.audit.services.verify_chain", side_effect=AssertionError("ricalcolo non atteso")):
            dashboard = self.client.get(reverse("core:dashboard"))
        self.assertContains(dashboard, "integro · verificato")
        self.assertContains(dashboard, "marca temporale")
        page = self.client.get(reverse("audit:checkpoints"))
        self.assertContains(page, "Ricevuta")
        self.assertContains(page, "Nessuna TSA configurata")
        self.assertEqual(self.client.get(reverse("audit:verify")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("audit:verify")), reverse("audit:checkpoints"))
        self.assertEqual(AuditCheckpoint.objects.count(), 2)
        receipt = self.client.get(reverse("audit:checkpoint_receipt", args=[AuditCheckpoint.objects.last().pk]))
        self.assertEqual(receipt["Content-Type"], "application/zip")
        self.assertTrue(AuditLog.objects.filter(action="download", object_repr__startswith="Ricevuta").exists())
        self.login(self.operator)
        self.assertRedirects(self.client.get(reverse("audit:checkpoints")), reverse("core:dashboard"),
                             fetch_redirect_response=False)

    def test_job_runs_nightly_verification(self):
        from fasas.core.jobs import run_job

        result = run_job("audit_verify")
        self.assertEqual((result["ok"], result["timestamped"]), (True, False))
        self.assertEqual(AuditCheckpoint.objects.get().source, "job")
