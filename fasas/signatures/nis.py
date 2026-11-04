"""
CIE senza PIN della carta: protocollo «NIS pinless» del Ministero dell'Interno (Manuale di integrazione per servizi
basati sul NIS, docs.italia.it; SDK di riferimento italia/cie-nis-java-sdk, licenza BSD-3).

Dalla carta si leggono senza PIN:
- EF.ID_Servizi (0x1001): il NIS, numero identificativo per i servizi (non riconducibile direttamente alla persona);
- EF.SERVIZI_INT.KPUB (0x1005): la chiave pubblica RSA dell'autenticazione interna;
- EF.SOD (0x1006): le impronte di NIS e chiave, firmate dal Document Signer del Ministero, certificato dalla CSCA.

Autenticità: il SOD è firmato da un Document Signer emesso dalla CSCA italiana e contiene le impronte del NIS e
della chiave letti. Originalità: la carta firma con la chiave privata (che non esce dal chip, non clonabile) una
sfida casuale del server («internal authentication»), che si verifica con la chiave pubblica del SOD.
Il NIS da solo si può copiare: per questo conta solo insieme all'autenticazione interna.
"""
import datetime
import hashlib

from django.conf import settings

from .providers import SignatureError

NIS_DG = ("A1", "00A1")      # impronta di EF.ID_Servizi nel SOD
KPUB_DG = ("A5", "00A5")     # impronta di EF.SERVIZI_INT.KPUB nel SOD
LDS_OID = "2.23.136.1.1.1"   # LDS Security Object (ICAO 9303)
CHALLENGE_BYTES = 16


class NisError(SignatureError):
    pass


# --- TLV (BER) minimo per i file della carta --------------------------------------------------------------------

def _tlv(data, pos=0):
    """(inizio del valore, fine del valore) del TLV che parte da pos; tag anche su più byte, lunghezze definite."""
    if pos >= len(data):
        raise NisError("Dati della carta incompleti.", "card_data")
    tag_end = pos + 1
    if data[pos] & 0x1F == 0x1F:  # tag su più byte
        while tag_end < len(data) and data[tag_end] & 0x80:
            tag_end += 1
        tag_end += 1
    if tag_end >= len(data):
        raise NisError("Dati della carta incompleti.", "card_data")
    length = data[tag_end]
    value_start = tag_end + 1
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or count > 4:
            raise NisError("Dati della carta non validi.", "card_data")
        length = int.from_bytes(data[value_start:value_start + count], "big")
        value_start += count
    value_end = value_start + length
    if value_end > len(data):
        raise NisError("Dati della carta incompleti.", "card_data")
    return value_start, value_end


def first_tlv(data):
    """Il primo elemento del file, senza i byte di riempimento che seguono (come lo calcola il SOD)."""
    _, end = _tlv(data, 0)
    return bytes(data[:end])


def _children(data, start, end):
    items, pos = [], start
    while pos < end:
        if data[pos] in (0x00, 0xFF):  # riempimento
            pos += 1
            continue
        value_start, value_end = _tlv(data, pos)
        items.append((value_start, value_end))
        pos = value_end
    return items


def rsa_public_numbers(kpub_file):
    """Modulo ed esponente da EF.SERVIZI_INT.KPUB (primo e secondo elemento della struttura)."""
    data = first_tlv(kpub_file)
    start, end = _tlv(data, 0)
    parts = _children(data, start, end)
    if len(parts) < 2:
        raise NisError("Chiave pubblica della carta non leggibile.", "card_data")
    modulus = int.from_bytes(data[parts[0][0]:parts[0][1]], "big")
    exponent = int.from_bytes(data[parts[1][0]:parts[1][1]], "big")
    if modulus.bit_length() < 1024 or exponent < 3:
        raise NisError("Chiave pubblica della carta non valida.", "card_data")
    return modulus, exponent


def verify_internal_auth(kpub_file, challenge, response):
    """La carta ha trasformato la sfida con la sua chiave privata: RSA pubblico, gli ultimi 16 byte = sfida."""
    modulus, exponent = rsa_public_numbers(kpub_file)
    size = (modulus.bit_length() + 7) // 8
    if len(challenge) != CHALLENGE_BYTES or not response or len(response) > size:
        raise NisError("Risposta della carta non valida.", "bad_signature")
    value = int.from_bytes(response, "big")
    if value >= modulus:
        raise NisError("Risposta della carta non valida.", "bad_signature")
    recovered = pow(value, exponent, modulus).to_bytes(size, "big")
    if recovered[-CHALLENGE_BYTES:] != challenge:
        raise NisError("La carta non ha dimostrato di essere una CIE originale (autenticazione interna).",
                       "bad_signature")
    return True


# --- SOD: autenticità di NIS e chiave pubblica -------------------------------------------------------------------

def _lds_classes():
    from asn1crypto import algos, core

    class DataGroupHash(core.Sequence):
        _fields = [("number", core.Integer), ("value", core.OctetString)]

    class DataGroupHashValues(core.SequenceOf):
        _child_spec = DataGroupHash

    class LDSSecurityObject(core.Sequence):
        _fields = [("version", core.Integer), ("hash_algorithm", algos.DigestAlgorithm),
                   ("hashes", DataGroupHashValues), ("version_info", core.Any, {"optional": True})]

    return LDSSecurityObject


def csca_certificates():
    """Certificati della CSCA italiana (https://csca-ita.interno.gov.it), file PEM indicato in FASAS_CIE_CSCA."""
    from cryptography import x509

    path = settings.FASAS_CIE_CSCA
    if not path:
        return []
    with open(path, "rb") as fh:
        data = fh.read()
    if b"-----BEGIN" in data:
        return x509.load_pem_x509_certificates(data)
    return [x509.load_der_x509_certificate(data)]


def _hash(name, data):
    names = {"sha1": "sha1", "sha224": "sha224", "sha256": "sha256", "sha384": "sha384", "sha512": "sha512"}
    if name not in names:
        raise NisError("Algoritmo di impronta del SOD non supportato.", "sod_invalid")
    return hashlib.new(names[name], data).digest()


def _verify_signer(cert, signer_info, signed_bytes):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    hash_name = signer_info["digest_algorithm"]["algorithm"].native
    hash_cls = {"sha1": hashes.SHA1, "sha224": hashes.SHA224, "sha256": hashes.SHA256, "sha384": hashes.SHA384,
                "sha512": hashes.SHA512}.get(hash_name)
    if hash_cls is None:
        raise NisError("Algoritmo del SOD non supportato.", "sod_invalid")
    algo = signer_info["signature_algorithm"]
    signature = signer_info["signature"].native
    key = cert.public_key()
    try:
        if isinstance(key, rsa.RSAPublicKey):
            if algo.signature_algo == "rsassa_pss":
                params = algo["parameters"]
                pad = padding.PSS(mgf=padding.MGF1(hash_cls()), salt_length=params["salt_length"].native)
            else:
                pad = padding.PKCS1v15()
            key.verify(signature, signed_bytes, pad, hash_cls())
        elif isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, signed_bytes, ec.ECDSA(hash_cls()))
        else:
            raise NisError("Chiave del Document Signer non supportata.", "sod_invalid")
    except InvalidSignature as exc:
        raise NisError("La firma del Ministero sui dati della carta non è valida.", "sod_invalid") from exc


def verify_sod(sod_file, nis, kpub_file, csca=None, now=None):
    """
    Controlla che NIS e chiave pubblica letti dalla carta siano quelli firmati dal Ministero (SOD) e che il Document
    Signer sia emesso dalla CSCA italiana configurata. Restituisce i dati del Document Signer.
    """
    from asn1crypto import cms
    from cryptography import x509

    csca = csca if csca is not None else csca_certificates()
    if not csca:
        raise NisError("Certificati della CSCA italiana non configurati (FASAS_CIE_CSCA).", "trust_not_configured")
    data = bytes(sod_file)
    if data[:1] != b"\x30":  # EF.SOD: un contenitore (es. tag 0x77) attorno al ContentInfo
        start, end = _tlv(data, 0)
        data = data[start:end]
    data = first_tlv(data)
    try:
        info = cms.ContentInfo.load(data)
        signed = info["content"]
        if info["content_type"].native != "signed_data":
            raise ValueError("non è SignedData")
        encap = signed["encap_content_info"]
        if encap["content_type"].dotted != LDS_OID:
            raise ValueError("contenuto non LDS")
        lds_bytes = encap["content"].native
        lds = _lds_classes().load(lds_bytes)
        hashes_by_dg = {item["number"].contents.hex().upper(): item["value"].native for item in lds["hashes"]}
        hash_name = lds["hash_algorithm"]["algorithm"].native
        signer_info = signed["signer_infos"][0]
        try:
            certs = [c.chosen for c in signed["certificates"]]
        except TypeError:  # nessun certificato nel SOD
            certs = []
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise NisError("Dati firmati della carta (SOD) non leggibili.", "sod_invalid") from exc

    nis_hash = next((hashes_by_dg[k] for k in NIS_DG if k in hashes_by_dg), None)
    kpub_hash = next((hashes_by_dg[k] for k in KPUB_DG if k in hashes_by_dg), None)
    if nis_hash != _hash(hash_name, bytes(nis)) or kpub_hash != _hash(hash_name, first_tlv(kpub_file)):
        raise NisError("NIS o chiave della carta diversi da quelli firmati dal Ministero.", "sod_invalid")

    signed_attrs = signer_info["signed_attrs"]
    if not signed_attrs.native:
        raise NisError("SOD senza attributi firmati.", "sod_invalid")
    digest = next((a["values"][0].native for a in signed_attrs if a["type"].native == "message_digest"), None)
    if digest != _hash(signer_info["digest_algorithm"]["algorithm"].native, lds_bytes):
        raise NisError("Impronta dei dati firmati della carta non corrispondente.", "sod_invalid")
    if not certs:
        raise NisError("Nel SOD manca il certificato del Document Signer.", "sod_invalid")
    signer = x509.load_der_x509_certificate(certs[0].dump())
    _verify_signer(signer, signer_info, b"\x31" + signed_attrs.dump()[1:])

    now = now or datetime.datetime.now(datetime.UTC)
    issuer = next((c for c in csca if c.subject == signer.issuer), None)
    if issuer is None:
        raise NisError("Il Document Signer non è emesso dalla CSCA italiana configurata.", "cert_untrusted")
    try:
        signer.verify_directly_issued_by(issuer)
    except Exception as exc:  # firma della CSCA non valida o algoritmi incoerenti
        raise NisError("Il Document Signer non è emesso dalla CSCA italiana configurata.", "cert_untrusted") from exc
    for cert, what in ((signer, "Document Signer"), (issuer, "CSCA")):
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise NisError(f"Certificato {what} della carta scaduto o non ancora valido.", "cert_expired")
    return {"document_signer": signer.subject.rfc4514_string()[:255], "csca": issuer.subject.rfc4514_string()[:255]}


def nis_hash(nis):
    return hashlib.sha256(bytes(nis)).hexdigest()


def kpub_hash(kpub_file):
    return hashlib.sha256(first_tlv(kpub_file)).hexdigest()
