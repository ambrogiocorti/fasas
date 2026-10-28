"""
Provider di firma digitale.

La firma prodotta è PAdES (PDF firmato, verificabile con Adobe Reader, DiKe, Firma OK!, ecc.).
Il valore legale dipende dal certificato:
- con un certificato qualificato di un QTSP (smart card esportata o firma remota) si ottiene
  una Firma Elettronica Qualificata (FEQ) ai sensi del Reg. eIDAS e del CAD;
- con un certificato non qualificato si ottiene una firma elettronica avanzata/semplice.
"""
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings


class SignatureError(Exception):
    pass


@dataclass
class CertificateInfo:
    subject: str
    issuer: str
    serial: str
    valid_from: object
    valid_to: object


def _name(x509_name):
    return x509_name.human_friendly


def inspect_pkcs12(p12_bytes: bytes, passphrase: str) -> CertificateInfo:
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        key, cert, _ = pkcs12.load_key_and_certificates(p12_bytes, passphrase.encode() if passphrase else None)
    except ValueError as exc:
        raise SignatureError("Certificato non leggibile o passphrase errata.") from exc
    if key is None or cert is None:
        raise SignatureError("Il file PKCS#12 deve contenere chiave privata e certificato.")
    return CertificateInfo(
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        serial=format(cert.serial_number, "X"),
        valid_from=cert.not_valid_before_utc,
        valid_to=cert.not_valid_after_utc,
    )


class BaseProvider:
    name = "base"

    def sign_pdf(self, pdf_bytes: bytes, credential, secret: str, reason: str, location: str) -> bytes:
        raise NotImplementedError


class PKCS12Provider(BaseProvider):
    name = "pkcs12"

    def sign_pdf(self, pdf_bytes, credential, secret, reason, location):
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers

        from fasas.core.encryption import read_encrypted

        p12 = read_encrypted(credential.storage_name)
        try:
            signer = signers.SimpleSigner.load_pkcs12_data(p12, other_certs=[], passphrase=secret.encode())
        except Exception as exc:  # pyHanko solleva tipi diversi a seconda dell'errore
            raise SignatureError("Passphrase errata o certificato non valido.") from exc
        if signer is None:
            raise SignatureError("Passphrase errata o certificato non valido.")

        timestamper = None
        if settings.FASAS_SIGNATURE_TSA_URL:
            from pyhanko.sign.timestamps import HTTPTimeStamper

            timestamper = HTTPTimeStamper(settings.FASAS_SIGNATURE_TSA_URL)

        writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes), strict=False)
        existing = len(_signature_fields(pdf_bytes))
        meta = signers.PdfSignatureMetadata(
            field_name=f"FirmaFASAS{existing + 1}",
            reason=reason or "Documento sanitario FASAS",
            location=location,
            subfilter=None,
        )
        out = signers.sign_pdf(writer, meta, signer=signer, timestamper=timestamper)
        return out.getvalue()


class RemoteQTSPProvider(BaseProvider):
    """
    Punto di integrazione per la firma remota qualificata (es. Aruba ARSS, InfoCert, Namirial).
    Ogni provider espone API proprietarie (SOAP/REST) con utente, password e OTP: implementare
    sign_pdf chiamando il servizio del prestatore scelto con il contratto della comunità.
    """

    name = "remote"

    def sign_pdf(self, pdf_bytes, credential, secret, reason, location):
        raise SignatureError(
            "Firma remota non configurata: è necessario un contratto con un prestatore qualificato "
            "e l'implementazione delle sue API in RemoteQTSPProvider."
        )


PROVIDERS = {"pkcs12": PKCS12Provider, "remote": RemoteQTSPProvider}


def provider_for(credential):
    return PROVIDERS[credential.kind]()


def _signature_fields(pdf_bytes):
    from pyhanko.pdf_utils.reader import PdfFileReader

    reader = PdfFileReader(BytesIO(pdf_bytes), strict=False)
    return list(reader.embedded_signatures)


def verify_pdf(pdf_bytes: bytes):
    """Verifica tutte le firme del PDF: integrità del contenuto e validità crittografica."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    reader = PdfFileReader(BytesIO(pdf_bytes), strict=False)
    results = []
    for sig in reader.embedded_signatures:
        try:
            status = validate_pdf_signature(sig, ValidationContext(allow_fetching=False))
            cert = status.signing_cert
            results.append({
                "field": sig.field_name,
                "signer": cert.subject.human_friendly if cert else "",
                "issuer": cert.issuer.human_friendly if cert else "",
                "signed_at": status.signer_reported_dt,
                "intact": status.intact,
                "valid": status.valid,
                "trusted": status.trusted,
                "covers_whole_document": status.coverage.name == "ENTIRE_FILE" if status.coverage else False,
                "summary": status.summary(),
            })
        except Exception as exc:  # una firma malformata non deve impedire di vedere le altre
            results.append({"field": sig.field_name, "error": str(exc), "intact": False, "valid": False, "trusted": False})
    return results
