"""
Provider di firma digitale.

La firma prodotta è PAdES (PDF firmato, verificabile con Adobe Reader, DiKe, Firma OK!, ecc.).
Il valore legale dipende dal certificato e da dove si trova la chiave:
- firma remota presso un prestatore qualificato (QTSP): è una Firma Elettronica Qualificata (FEQ, Reg. eIDAS
  e CAD) solo se il certificato dichiara di essere qualificato con chiave in un dispositivo qualificato
  (QcCompliance e QcSSCD) e la catena risulta verificata con le CA del prestatore configurate;
- certificato personale in un file PKCS#12: la chiave non è in un dispositivo qualificato, quindi la firma
  non è mai qualificata;
- CIE (vedi fasas.signatures.cie): Firma Elettronica Avanzata, mai qualificata.
"""
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings


class SignatureError(Exception):
    """Errore di firma con un messaggio per l'utente e un codice stabile (usato dalle API e dall'audit)."""

    def __init__(self, message, code="error"):
        super().__init__(message)
        self.code = code


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


LEVELS = ("B-B", "B-T", "B-LT", "B-LTA")


def signature_level():
    """Livello PAdES: B-B (base), B-T (+ marca temporale), B-LT (+ dati di validazione), B-LTA (+ marca d'archivio)."""
    level = (settings.FASAS_SIGNATURE_LEVEL or "").upper().removeprefix("PADES-")
    if not level:
        level = "B-T" if settings.FASAS_SIGNATURE_TSA_URL else "B-B"
    if level not in LEVELS:
        raise SignatureError(f"FASAS_SIGNATURE_LEVEL non valido: usare {', '.join(LEVELS)}.")
    if level != "B-B" and not settings.FASAS_SIGNATURE_TSA_URL:
        raise SignatureError(f"Il livello PAdES-{level} richiede una marca temporale: configurare FASAS_SIGNATURE_TSA_URL.")
    return level


def timestamper():
    if not settings.FASAS_SIGNATURE_TSA_URL:
        return None
    from pyhanko.sign.timestamps import HTTPTimeStamper

    auth = None
    if settings.FASAS_SIGNATURE_TSA_USER:
        auth = (settings.FASAS_SIGNATURE_TSA_USER, settings.FASAS_SIGNATURE_TSA_PASSWORD)
    return HTTPTimeStamper(settings.FASAS_SIGNATURE_TSA_URL, auth=auth, timeout=20)


def trust_roots():
    """Certificati radice dei prestatori qualificati (file PEM in FASAS_SIGNATURE_TRUST_ROOTS)."""
    path = settings.FASAS_SIGNATURE_TRUST_ROOTS
    if not path:
        return []
    from asn1crypto import pem, x509

    with open(path, "rb") as fh:
        data = fh.read()
    if not pem.detect(data):
        return [x509.Certificate.load(data)]
    return [x509.Certificate.load(der) for _, _, der in pem.unarmor(data, multiple=True)]


def signature_metadata(field_name, reason, location, chain=()):
    from pyhanko.sign import signers
    from pyhanko_certvalidator import ValidationContext

    level = signature_level()
    extra = {}
    if level in ("B-LT", "B-LTA"):
        roots = trust_roots() or [c for c in chain if c.self_signed]
        if not roots:
            raise SignatureError("Per il livello B-LT serve il certificato radice del prestatore "
                                 "(FASAS_SIGNATURE_TRUST_ROOTS).")
        extra = {"embed_validation_info": True, "use_pades_lta": level == "B-LTA",
                 "validation_context": ValidationContext(trust_roots=roots, allow_fetching=True)}
    return signers.PdfSignatureMetadata(
        field_name=field_name, reason=reason or "Documento sanitario FASAS", location=location,
        md_algorithm="sha256", **extra,
    )


QC_COMPLIANCE = "0.4.0.1862.1.1"  # certificato qualificato (ETSI EN 319 412-5)
QC_SSCD = "0.4.0.1862.1.4"        # chiave in un dispositivo qualificato per la creazione di firme


def qc_statements(cert):
    """Identificativi delle QCStatements del certificato (asn1crypto)."""
    from asn1crypto import core

    class QcStatement(core.Sequence):
        _fields = [("statement_id", core.ObjectIdentifier), ("statement_info", core.Any, {"optional": True})]

    class QcStatements(core.SequenceOf):
        _child_spec = QcStatement

    for ext in cert["tbs_certificate"]["extensions"] or []:
        if ext["extn_id"].dotted == "1.3.6.1.5.5.7.1.3":
            try:
                return {item["statement_id"].dotted for item in QcStatements.load(ext["extn_value"].contents)}
            except ValueError:
                return set()
    return set()


def legal_level(signed_pdf, kind):
    """Valore giuridico dell'ultima firma apposta: «qualificata» solo con tutti i requisiti verificabili."""
    from pyhanko.pdf_utils.reader import PdfFileReader

    from .models import LegalLevel

    if kind != "remote":
        return LegalLevel.FE
    signatures = PdfFileReader(BytesIO(signed_pdf), strict=False).embedded_signatures
    if not signatures:
        return LegalLevel.FE
    statements = qc_statements(signatures[-1].signer_cert)
    trusted = verify_pdf(signed_pdf)[-1].get("trusted")
    return LegalLevel.FEQ if {QC_COMPLIANCE, QC_SSCD} <= statements and trusted else LegalLevel.FE


def next_field_name(pdf_bytes):
    return f"FirmaFASAS{len(_signature_fields(pdf_bytes)) + 1}"


class BaseProvider:
    name = "base"

    def sign_pdf(self, pdf_bytes: bytes, credential, secrets: dict, reason: str, location: str) -> bytes:
        raise NotImplementedError


class PKCS12Provider(BaseProvider):
    name = "pkcs12"

    def sign_pdf(self, pdf_bytes, credential, secrets, reason, location):
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers

        from fasas.core.encryption import read_encrypted

        p12 = read_encrypted(credential.storage_name)
        try:
            signer = signers.SimpleSigner.load_pkcs12_data(
                p12, other_certs=[], passphrase=(secrets.get("passphrase") or "").encode())
        except Exception as exc:  # pyHanko solleva tipi diversi a seconda dell'errore
            raise SignatureError("Passphrase errata o certificato non valido.") from exc
        if signer is None:
            raise SignatureError("Passphrase errata o certificato non valido.")
        chain = list(signer.cert_registry)
        meta = signature_metadata(next_field_name(pdf_bytes), reason, location, chain)
        writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes), strict=False)
        out = signers.PdfSigner(meta, signer=signer, timestamper=timestamper()).sign_pdf(writer)
        return out.getvalue()


class RemoteCSCProvider(BaseProvider):
    """Firma remota qualificata tramite API CSC (vedi fasas.signatures.csc)."""

    name = "remote"

    def sign_pdf(self, pdf_bytes, credential, secrets, reason, location):
        from . import csc

        if not credential.remote_credential_id:
            raise SignatureError("Firma remota non configurata per il tuo utente: completare la configurazione.")
        config = csc.CSCConfig.from_settings()
        field_name = next_field_name(pdf_bytes)
        signed, _ = csc.run(csc.sign_pdf_remote(
            config, credential, pdf_bytes, username=credential.remote_user_id,
            password=secrets.get("password", ""), pin=secrets.get("pin", ""), otp=secrets.get("otp", ""),
            token=secrets.get("token"), reason=reason, location=location, timestamper=timestamper(),
            build_metadata=lambda info: signature_metadata(field_name, reason, location,
                                                           [info.signing_cert, *info.chain]),
        ))
        return signed


PROVIDERS = {"pkcs12": PKCS12Provider, "remote": RemoteCSCProvider}


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

    from .external import intermediate_certs, key_usage_settings
    from .external import trust_roots as cie_roots

    reader = PdfFileReader(BytesIO(pdf_bytes), strict=False)
    roots = trust_roots() + cie_roots()
    results = []
    for sig in reader.embedded_signatures:
        try:
            # digitalSignature o nonRepudiation: il valore giuridico si legge da «legal_level», non da qui
            status = validate_pdf_signature(
                sig, ValidationContext(trust_roots=roots or None, other_certs=intermediate_certs(), allow_fetching=False),
                key_usage_settings=key_usage_settings())
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
                "timestamped": status.timestamp_validity is not None,
                "qualified_statements": {QC_COMPLIANCE, QC_SSCD} <= qc_statements(cert) if cert else False,
            })
        except Exception as exc:  # una firma malformata non deve impedire di vedere le altre
            results.append({"field": sig.field_name, "error": str(exc), "intact": False, "valid": False, "trusted": False})
    return results
