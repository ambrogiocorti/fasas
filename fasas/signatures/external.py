"""
Motore PAdES a firma esterna (FASAS Sign).

La chiave privata non lascia mai il dispositivo del firmatario (CIE, smart card): il server prepara il PDF
e gli attributi firmati CMS, il dispositivo restituisce solo il valore della firma RSA, il server lo verifica
con la chiave pubblica del certificato e lo incorpora nel PDF.

1. prepare(): riserva lo spazio per la firma con una revisione incrementale (le firme precedenti restano
   valide), calcola l'impronta del /ByteRange e gli attributi firmati PAdES (content-type, message-digest,
   signing-certificate-v2). Il dispositivo firma la codifica DER di questi attributi.
2. check_signature_value(): verifica crittografica del valore restituito dal dispositivo.
3. finish(): costruisce la busta CMS, aggiunge la marca temporale solo se è configurata una TSA reale
   (RFC 3161) e la incorpora nel PDF preparato.
4. validate_last_signature(): verifica con pyHanko la firma appena apposta (integrità, copertura, catena
   di certificazione, revoca quando i dati sono disponibili).
"""
import asyncio
import base64
import datetime
import hashlib
import re
from dataclasses import asdict, dataclass
from io import BytesIO

from django.conf import settings

from .providers import SignatureError

CF_RE = re.compile(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]")
# DigestInfo DER di SHA-256 (RFC 8017 §9.2): con il meccanismo CKM_RSA_PKCS il dispositivo firma prefisso + impronta
SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
SIGNATURE_MECHANISM = "sha256_rsa"
MIN_RSA_BITS = 2048


def _run(coro):
    return asyncio.run(coro)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text, what="dato") -> bytes:
    try:
        return base64.b64decode(text or "", validate=True)
    except (ValueError, TypeError) as exc:
        raise SignatureError(f"{what} non valido (base64).") from exc


# --- Certificati -------------------------------------------------------------------------------------------

def load_certificate(der: bytes):
    """Certificato X.509 in DER (asn1crypto, come richiesto da pyHanko)."""
    from asn1crypto import x509
    from cryptography import x509 as cx509

    try:
        cx509.load_der_x509_certificate(der)  # parsing completo e rigoroso: un DER troncato o alterato fallisce qui
        return x509.Certificate.load(der)
    except (ValueError, TypeError) as exc:
        raise SignatureError("Certificato non leggibile.", "cert_invalid") from exc


def fiscal_codes_in(cert) -> set:
    """Codici fiscali presenti nel soggetto del certificato (es. serialNumber «TINIT-…» o CN «CF/…»)."""
    found = set()
    for rdn in cert.subject.chosen:
        for attr in rdn:
            value = attr["value"].native
            if isinstance(value, str):
                found.update(CF_RE.findall(value.upper()))
    return found


def certificate_info(cert) -> dict:
    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives.asymmetric import rsa

    parsed = cx509.load_der_x509_certificate(cert.dump())
    public_key = parsed.public_key()
    try:
        key_usage = parsed.extensions.get_extension_for_class(cx509.KeyUsage).value
        usages = {name for name in ("digital_signature", "content_commitment")
                  if getattr(key_usage, name)}
    except cx509.ExtensionNotFound:
        usages = set()
    return {
        "subject": parsed.subject.rfc4514_string()[:255],
        "issuer": parsed.issuer.rfc4514_string()[:255],
        "serial": format(parsed.serial_number, "X"),
        "valid_from": parsed.not_valid_before_utc,
        "valid_to": parsed.not_valid_after_utc,
        "fingerprint": hashlib.sha256(cert.dump()).hexdigest(),
        "key_bits": getattr(public_key, "key_size", 0),
        "is_rsa": isinstance(public_key, rsa.RSAPublicKey),
        "key_usage": sorted(usages),
        "fiscal_codes": sorted(fiscal_codes_in(cert)),
        "common_name": ", ".join(a.value for a in parsed.subject.get_attributes_for_oid(cx509.NameOID.COMMON_NAME)),
    }


def check_certificate_for_user(cert, user, now=None) -> dict:
    """Il certificato deve essere valido ora, RSA ≥ 2048 bit, utilizzabile per firmare e intestato all'utente."""
    info = certificate_info(cert)
    now = now or datetime.datetime.now(datetime.UTC)
    if not (info["valid_from"] <= now <= info["valid_to"]):
        raise SignatureError("Il certificato della carta è scaduto o non ancora valido.", "cert_expired")
    if not info["is_rsa"] or info["key_bits"] < MIN_RSA_BITS:
        raise SignatureError("Il certificato della carta non usa una chiave RSA di almeno 2048 bit.", "cert_invalid")
    if not info["key_usage"]:
        raise SignatureError("Il certificato della carta non è abilitato alla firma (key usage).", "cert_invalid")
    expected = (user.fiscal_code or "").strip().upper()
    if not expected:
        raise SignatureError("Nel tuo profilo FASAS manca il codice fiscale: chiedi all'amministratore di inserirlo.",
                             "missing_fiscal_code")
    if not info["fiscal_codes"]:
        raise SignatureError("Il codice fiscale del titolare non è leggibile dal certificato della carta.",
                             "cert_mismatch")
    if expected not in info["fiscal_codes"]:
        raise SignatureError("La carta appoggiata non appartiene all'utente collegato al FASAS.", "cert_mismatch")
    return info


def trust_roots():
    """Certificati radice della CIE (file PEM in FASAS_CIE_TRUST_ROOTS) ed eventuali intermedi."""
    return _load_pem_bundle(settings.FASAS_CIE_TRUST_ROOTS)


def intermediate_certs():
    return _load_pem_bundle(settings.FASAS_CIE_INTERMEDIATES)


def _load_pem_bundle(path):
    if not path:
        return []
    from asn1crypto import pem, x509

    with open(path, "rb") as fh:
        data = fh.read()
    if not pem.detect(data):
        return [x509.Certificate.load(data)]
    return [x509.Certificate.load(der) for _, _, der in pem.unarmor(data, multiple=True)]


def validation_context(moment=None):
    from pyhanko_certvalidator import ValidationContext

    mode = settings.FASAS_CIE_REVOCATION
    return ValidationContext(
        trust_roots=trust_roots() or None, other_certs=intermediate_certs(), moment=moment,
        allow_fetching=mode in ("soft-fail", "hard-fail"),
        revocation_mode="hard-fail" if mode == "hard-fail" else "soft-fail",
    )


def key_usage_settings():
    """Firma elettronica avanzata: basta uno tra digitalSignature e nonRepudiation (la FEQ richiede nonRepudiation)."""
    from pyhanko.sign.validation.settings import KeyUsageConstraints

    return KeyUsageConstraints(key_usage={"digital_signature", "non_repudiation"}, match_all_key_usages=False)


def validate_certificate_chain(cert):
    """Verifica la catena verso le CA della CIE configurate (e la revoca, se abilitata e raggiungibile)."""
    from pyhanko_certvalidator import CertificateValidator
    from pyhanko_certvalidator.errors import PathBuildingError, PathValidationError, RevokedError

    if not trust_roots():
        raise SignatureError("CA della CIE non configurate sul server (FASAS_CIE_TRUST_ROOTS): firma non disponibile.",
                             "trust_not_configured")
    validator = CertificateValidator(cert, validation_context=validation_context())
    try:
        _run(validator.async_validate_usage(key_usage=set()))
    except RevokedError as exc:
        raise SignatureError("Il certificato della carta risulta revocato.", "cert_revoked") from exc
    except (PathBuildingError, PathValidationError) as exc:
        raise SignatureError("Il certificato della carta non è emesso da una CA della CIE riconosciuta.",
                             "cert_untrusted") from exc


# --- Preparazione e completamento --------------------------------------------------------------------------

@dataclass
class PreparedSignature:
    """Stato tra la preparazione e il completamento: il PDF preparato si conserva a parte, cifrato."""

    field_name: str
    document_digest: str     # base64 dell'impronta SHA-256 del /ByteRange
    reserved_start: int
    reserved_end: int
    signed_attrs: str        # base64 della codifica DER degli attributi firmati (ciò che il dispositivo firma)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    @property
    def to_be_signed(self) -> bytes:
        return unb64(self.signed_attrs)

    @property
    def digest(self) -> bytes:
        return hashlib.sha256(self.to_be_signed).digest()

    @property
    def digest_info(self) -> bytes:
        return SHA256_DIGEST_INFO_PREFIX + self.digest


def _external_signer(cert, chain, signature_value=None):
    from asn1crypto import algos
    from pyhanko.sign import signers
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    size = (certificate_info(cert)["key_bits"] + 7) // 8
    return signers.ExternalSigner(
        signing_cert=cert, cert_registry=SimpleCertificateStore.from_certs(list(chain)),
        signature_value=signature_value if signature_value is not None else bytes(size),
        signature_mechanism=algos.SignedDigestAlgorithm({"algorithm": SIGNATURE_MECHANISM}),
    )


def prepare(pdf_bytes, cert, chain=(), *, field_name, reason, location, with_timestamp=False):
    """Restituisce (PreparedSignature, PDF preparato con lo spazio riservato alla firma)."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    from .providers import timestamper

    async def _prepare():
        external = _external_signer(cert, chain)
        meta = signers.PdfSignatureMetadata(
            field_name=field_name, md_algorithm="sha256", subfilter=fields.SigSeedSubFilter.PADES,
            reason=reason or "Documento sanitario FASAS", location=location,
        )
        writer = IncrementalPdfFileWriter(BytesIO(pdf_bytes), strict=False)
        # Lo spazio per la marca temporale va riservato subito: dopo la preparazione il PDF non cambia più
        pdf_signer = signers.PdfSigner(meta, signer=external)
        reserved = 8192 + (8192 if with_timestamp else 0) + sum(len(c.dump()) for c in chain) * 2
        digest, _, output = await pdf_signer.async_digest_doc_for_signing(writer, bytes_reserved=reserved)
        attrs = await external.signed_attrs(digest.document_digest, "sha256", use_pades=True)
        return digest, output.getvalue(), attrs.dump()

    if with_timestamp and timestamper() is None:
        raise SignatureError("Marca temporale richiesta ma nessuna TSA configurata.")
    try:
        digest, prepared_pdf, attrs = _run(_prepare())
    except SignatureError:
        raise
    except Exception as exc:  # PDF danneggiati o cifrati sollevano eccezioni di tipo diverso
        raise SignatureError("Il PDF non può essere preparato per la firma (file danneggiato o protetto).") from exc
    return PreparedSignature(
        field_name=field_name, document_digest=b64(digest.document_digest),
        reserved_start=digest.reserved_region_start, reserved_end=digest.reserved_region_end, signed_attrs=b64(attrs),
    ), prepared_pdf


def check_signature_value(cert, prepared: PreparedSignature, signature: bytes):
    """RSA PKCS#1 v1.5 con SHA-256 sugli attributi firmati: se il dispositivo ha firmato altro, si rifiuta."""
    from cryptography import x509 as cx509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    public_key = cx509.load_der_x509_certificate(cert.dump()).public_key()
    if len(signature) != (public_key.key_size + 7) // 8:
        raise SignatureError("Il valore di firma restituito dalla carta ha una lunghezza inattesa.", "bad_signature")
    try:
        public_key.verify(signature, prepared.to_be_signed, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise SignatureError("La firma restituita dalla carta non corrisponde al documento preparato.",
                             "bad_signature") from exc


def finish(prepared_pdf: bytes, prepared: PreparedSignature, cert, chain, signature: bytes, with_timestamp=False):
    """Incorpora la busta CMS nel PDF preparato e restituisce il PDF firmato."""
    from asn1crypto import cms
    from pyhanko.sign.signers.pdf_byterange import PreparedByteRangeDigest
    from pyhanko.sign.signers.pdf_signer import PdfTBSDocument

    from .providers import timestamper

    async def _finish():
        external = _external_signer(cert, chain, signature)
        attrs = cms.CMSAttributes.load(prepared.to_be_signed)
        signed_data = await external.async_sign_prescribed_attributes(
            "sha256", attrs, timestamper=timestamper() if with_timestamp else None)
        digest = PreparedByteRangeDigest(
            document_digest=unb64(prepared.document_digest), reserved_region_start=prepared.reserved_start,
            reserved_region_end=prepared.reserved_end,
        )
        output = BytesIO(prepared_pdf)
        await PdfTBSDocument.async_finish_signing(output, digest, signed_data)
        return output.getvalue()

    try:
        return _run(_finish())
    except Exception as exc:
        raise SignatureError("Impossibile completare la busta di firma nel PDF.", "embed_failed") from exc


def validate_last_signature(signed_pdf: bytes, cert, expected_field: str) -> dict:
    """Verifica la firma appena apposta: deve essere integra, valida, coprire tutto il file e risultare del certificato atteso."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    reader = PdfFileReader(BytesIO(signed_pdf), strict=False)
    signatures = [s for s in reader.embedded_signatures if s.field_name == expected_field]
    if len(signatures) != 1:
        raise SignatureError("La firma apposta non è stata trovata nel PDF.", "verify_failed")
    status = validate_pdf_signature(signatures[0], validation_context(), key_usage_settings=key_usage_settings())
    result = {
        "field": expected_field, "intact": status.intact, "valid": status.valid, "trusted": status.trusted,
        "coverage": status.coverage.name if status.coverage else "", "summary": status.summary(),
        "timestamped": status.timestamp_validity is not None,
        "signer_fingerprint": hashlib.sha256(status.signing_cert.dump()).hexdigest() if status.signing_cert else "",
        "revocation_mode": settings.FASAS_CIE_REVOCATION,
    }
    if not (status.intact and status.valid):
        raise SignatureError("La verifica della firma apposta non è riuscita.", "verify_failed")
    if result["coverage"] != "ENTIRE_FILE":
        raise SignatureError("La firma apposta non copre l'intero documento.", "verify_failed")
    if result["signer_fingerprint"] != hashlib.sha256(cert.dump()).hexdigest():
        raise SignatureError("Il certificato nella firma non è quello della carta.", "verify_failed")
    if not status.trusted:
        raise SignatureError("La catena di certificazione della firma non è verificabile.", "cert_untrusted")
    return result
