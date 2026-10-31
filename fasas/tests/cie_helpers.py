"""
Strumenti di prova per la firma con CIE.

Non c'è una CIE: si usano una CA di prova e certificati di prova con codici fiscali di prova. Le chiavi sono
chiavi RSA vere, quindi le firme sono crittograficamente reali, ma NON sono firme con CIE né hanno valore legale.
Il collaudo con una CIE reale su un dispositivo reale resta da fare (vedi docs/FIRMA_CIE.md).
"""
import base64
import datetime
import json
import os
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.x509.oid import NameOID

NOW = datetime.datetime.now(datetime.UTC)


def _name(**attrs):
    oids = {"cn": NameOID.COMMON_NAME, "serial": NameOID.SERIAL_NUMBER, "given": NameOID.GIVEN_NAME,
            "surname": NameOID.SURNAME, "o": NameOID.ORGANIZATION_NAME, "c": NameOID.COUNTRY_NAME}
    return x509.Name([x509.NameAttribute(oids[k], v) for k, v in attrs.items()])


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build(subject, issuer, public_key, issuer_key, *, ca=False, days=(-1, 365), key_usage=None):
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(public_key)
               .serial_number(x509.random_serial_number())
               .not_valid_before(NOW + datetime.timedelta(days=days[0]))
               .not_valid_after(NOW + datetime.timedelta(days=days[1]))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    usage = dict(digital_signature=not ca, content_commitment=False, key_encipherment=False, data_encipherment=False,
                 key_agreement=False, key_cert_sign=ca, crl_sign=ca, encipher_only=False, decipher_only=False)
    usage.update(key_usage or {})
    builder = builder.add_extension(x509.KeyUsage(**usage), critical=True)
    return builder.sign(issuer_key, hashes.SHA256())


class TestPKI:
    """CA radice di prova → CA intermedia di prova → certificati «tipo CIE» (CF nel serialNumber e nel CN)."""

    def __init__(self, name="Prova"):
        self.root_key = _key()
        self.root_name = _name(c="IT", o=f"FASAS {name} (solo test)", cn=f"CA radice di prova {name}")
        self.root = _build(self.root_name, self.root_name, self.root_key.public_key(), self.root_key, ca=True,
                           days=(-30, 3650))
        self.inter_key = _key()
        self.inter_name = _name(c="IT", o=f"FASAS {name} (solo test)", cn=f"CA intermedia di prova {name}")
        self.inter = _build(self.inter_name, self.root_name, self.inter_key.public_key(), self.root_key, ca=True,
                            days=(-30, 3000))
        self.dir = tempfile.mkdtemp(prefix="fasas-cie-pki-")
        self.roots_path = self._write("roots.pem", [self.root])
        self.inter_path = self._write("intermediates.pem", [self.inter])

    def _write(self, name, certs):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            for cert in certs:
                fh.write(cert.public_bytes(serialization.Encoding.PEM))
        return path

    def card(self, fiscal_code, given="Marta", surname="Medico", *, days=(-1, 365), key=None, key_usage=None):
        key = key or _key()
        # Come la CIE secondo gli SDK di PagoPA: codice fiscale nel CN, numero del documento nel serialNumber
        subject = _name(c="IT", given=given, surname=surname, serial="CA00000AA", cn=fiscal_code)
        cert = _build(subject, self.inter_name, key.public_key(), self.inter_key, days=days, key_usage=key_usage)
        return TestCard(key, cert)

    def settings(self, **extra):
        return {"FASAS_CIE_TRUST_ROOTS": self.roots_path, "FASAS_CIE_INTERMEDIATES": self.inter_path,
                "FASAS_CIE_REVOCATION": "off", "FASAS_CIE_ALLOW_HTTP": True, "FASAS_SIGNATURE_TSA_URL": "", **extra}


class TestCard:
    """Chiave e certificato di prova al posto della carta (solo nei test)."""

    def __init__(self, key, cert):
        self.key, self.cert = key, cert

    @property
    def der_b64(self):
        return base64.b64encode(self.cert.public_bytes(serialization.Encoding.DER)).decode()

    def sign(self, to_be_signed_b64):
        """Come CKM_SHA256_RSA_PKCS: hash SHA-256 e firma PKCS#1 v1.5."""
        return base64.b64encode(self.key.sign(base64.b64decode(to_be_signed_b64), padding.PKCS1v15(),
                                              hashes.SHA256())).decode()

    def sign_digest_info(self, digest_info_b64):
        """Come CKM_RSA_PKCS su un DigestInfo già pronto (il DigestInfo contiene già l'OID di SHA-256)."""
        digest_info = base64.b64decode(digest_info_b64)
        digest = digest_info[-32:]
        return base64.b64encode(self.key.sign(digest, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))).decode()


class DeviceClient:
    """Il FASAS Signer visto dal server: chiamate alle API con il token del dispositivo."""

    def __init__(self, client, token=None):
        self.client, self.token = client, token

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"} if self.token else {}

    def post(self, path, data=None):
        response = self.client.post(f"/api/firma/v1/{path}", data=json.dumps(data or {}),
                                    content_type="application/json", **self._headers())
        return response.status_code, response.json()

    def get(self, path):
        response = self.client.get(f"/api/firma/v1/{path}", **self._headers())
        return response.status_code, response.json()

    def pair(self, code, name="PC ambulatorio", platform="linux"):
        status, data = self.post("abbina/", {"code": code, "name": name, "platform": platform, "app_version": "test"})
        if status == 201:
            self.token = data["token"]
        return status, data

    def sign_flow(self, request_id, card, *, mechanism="sha256"):
        """Flusso completo come il Signer: presa in carico, carta, certificato, PIN, firma."""
        status, data = self.post(f"richieste/{request_id}/prendi/")
        assert status == 200, data
        status, data = self.post(f"richieste/{request_id}/stato/", {"nonce": data["nonce"], "state": "card"})
        assert status == 200, data
        status, data = self.post(f"richieste/{request_id}/certificato/", {"nonce": data["nonce"],
                                                                          "certificate": card.der_b64})
        if status != 200:
            return status, data
        prepared = data
        status, data = self.post(f"richieste/{request_id}/stato/", {"nonce": prepared["nonce"], "state": "signing"})
        assert status == 200, data
        value = card.sign(prepared["to_be_signed"]) if mechanism == "sha256" else card.sign_digest_info(
            prepared["digest_info"])
        return self.post(f"richieste/{request_id}/firma/", {"nonce": data["nonce"], "signature": value})


def record_acceptance(user):
    """Accettazione delle condizioni della FEA già registrata (per i test che provano la firma dei documenti)."""
    from django.utils import timezone

    from fasas.signatures.models import FEAAcceptance, SignatureRequest

    now = timezone.now()
    request = SignatureRequest.objects.create(user=user, purpose=SignatureRequest.Purpose.ACCEPTANCE, status="signed",
                                              version_sha256="0" * 64, verify_code="PROV-A000", nonce_hash="-",
                                              expires_at=now, completed_at=now)
    return FEAAcceptance.objects.create(user=user, request=request, terms_version="test", terms_sha256="0" * 64,
                                        signed_storage="", signed_sha256="0" * 64, certificate="",
                                        certificate_subject="test", certificate_serial="0", retain_until=now.date())
