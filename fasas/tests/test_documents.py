import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from fasas.audit.models import AuditLog
from fasas.documents.models import Document
from fasas.documents.services import create_document, read_version
from fasas.reports.pdf import Document as PdfDocument
from fasas.signatures.providers import verify_pdf
from fasas.signatures.services import register_pkcs12, sign_version

from .base import FasasTestCase


def sample_pdf():
    doc = PdfDocument("Relazione di prova")
    doc.text("Contenuto sanitario riservato")
    return doc.build()


def self_signed_p12(passphrase):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Dott.ssa Marta Medico")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(
        b"firma", key, cert, None, serialization.BestAvailableEncryption(passphrase.encode()))


class DocumentTests(FasasTestCase):
    def test_upload_is_encrypted_versioned_and_audited(self):
        pdf = sample_pdf()
        document = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione",
                                   uploaded=SimpleUploadedFile("relazione.pdf", pdf, "application/pdf"),
                                   user=self.coordinator)
        version = document.current_version
        with default_storage.open(version.storage_name, "rb") as handle:
            stored = handle.read()
        self.assertNotIn(b"%PDF", stored)  # sul disco solo dati cifrati
        self.assertEqual(read_version(version, user=self.operator), pdf)
        self.assertTrue(AuditLog.objects.filter(action="download", object_id=str(version.pk)).exists())

        self.login(self.coordinator)
        response = self.client.post(f"/documenti/{document.pk}/versione/", {
            "file": SimpleUploadedFile("relazione_v2.pdf", pdf + b"%%", "application/pdf"), "note": "aggiornata"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(document.versions.count(), 2)
        response = self.client.get(f"/documenti/versione/{document.current_version.pk}/scarica/")
        self.assertEqual(response.content, pdf + b"%%")

    def test_size_and_extension_limits(self):
        from fasas.core.models import SystemConfig

        config = SystemConfig.get()
        config.max_upload_mb = 1
        config.save()
        self.login(self.coordinator)
        big = SimpleUploadedFile("grande.pdf", b"0" * (1024 * 1024 + 1), "application/pdf")
        response = self.client.post(f"/documenti/ospite/{self.guest.pk}/nuovo/",
                                    {"category": "other", "title": "Grande", "file": big})
        self.assertContains(response, "dimensione massima")
        exe = SimpleUploadedFile("virus.exe", b"MZ", "application/octet-stream")
        response = self.client.post(f"/documenti/ospite/{self.guest.pk}/nuovo/",
                                    {"category": "other", "title": "Exe", "file": exe})
        self.assertContains(response, "non ammessa")
        self.assertFalse(Document.objects.exists())

    def test_pades_signature_roundtrip(self):
        document = create_document(self.guest, Document.Category.PAI, "PAI", user=self.coordinator,
                                   data=sample_pdf(), filename="pai.pdf")
        register_pkcs12(self.doctor, self_signed_p12("segreta"), "segreta")
        signature = sign_version(document.current_version, self.doctor, "segreta", "Approvazione PAI")
        signed = read_version(signature.signed_version, audit=False)
        results = verify_pdf(signed)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["intact"])
        self.assertTrue(results[0]["valid"])
        self.assertIn("Marta", results[0]["signer"])
        self.assertTrue(signature.signed_version.is_signed)
        self.assertEqual(document.versions.count(), 2)

    def test_wrong_passphrase_and_permission(self):
        from fasas.signatures.providers import SignatureError

        document = create_document(self.guest, Document.Category.PAI, "PAI", user=self.coordinator,
                                   data=sample_pdf(), filename="pai.pdf")
        register_pkcs12(self.doctor, self_signed_p12("segreta"), "segreta")
        with self.assertRaises(SignatureError):
            sign_version(document.current_version, self.doctor, "sbagliata")
        with self.assertRaises(SignatureError):
            sign_version(document.current_version, self.operator, "segreta")
