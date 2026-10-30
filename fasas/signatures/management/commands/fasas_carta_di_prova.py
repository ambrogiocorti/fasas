"""
Carta di prova per provare la firma con CIE senza lettore NFC (solo installazioni di prova, DJANGO_DEBUG=1).

Crea una CA di prova («SOLO PROVA – NON È UNA CIE») e, per l'utente indicato, una «carta» software: un file
PKCS#12 protetto dal PIN e il relativo certificato con il codice fiscale dell'utente. Il FASAS Signer la usa al posto
del Software CIE con l'opzione --carta-di-prova. Le firme sono crittograficamente vere ma senza alcun valore legale:
il FASAS le registra come «carta di prova» e le rifiuta quando DJANGO_DEBUG non è attivo.
"""
import datetime
import re
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from fasas.signatures.external import CF_RE, TEST_MARKER

TEST_FISCAL_CODE = "PRVFSS80A01H501U"  # codice fiscale fittizio, usato solo se l'utente non ne ha uno


def _name(**attrs):
    oids = {"c": NameOID.COUNTRY_NAME, "o": NameOID.ORGANIZATION_NAME, "cn": NameOID.COMMON_NAME,
            "given": NameOID.GIVEN_NAME, "surname": NameOID.SURNAME, "serial": NameOID.SERIAL_NUMBER}
    return x509.Name([x509.NameAttribute(oids[k], v) for k, v in attrs.items() if v])


def _certificate(subject, issuer, public_key, issuer_key, *, ca, years):
    now = datetime.datetime.now(datetime.UTC)
    usage = dict(digital_signature=not ca, content_commitment=False, key_encipherment=False, data_encipherment=False,
                 key_agreement=False, key_cert_sign=ca, crl_sign=ca, encipher_only=False, decipher_only=False)
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365 * years))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(**usage), critical=True)
            .sign(issuer_key, hashes.SHA256()))


def _pem(path, objects):
    with open(path, "wb") as fh:
        for obj in objects:
            fh.write(obj.public_bytes(serialization.Encoding.PEM))


def _private(path, key):
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))


class Command(BaseCommand):
    help = "Crea una carta di prova per provare la firma con CIE senza lettore (solo con DJANGO_DEBUG=1)."

    def add_arguments(self, parser):
        parser.add_argument("--utente", default="medico", help="utente FASAS che firmerà (predefinito: medico)")
        parser.add_argument("--pin", default="1234", help="PIN della carta di prova (predefinito: 1234)")
        parser.add_argument("--cartella", default="", help="dove salvare i file (predefinito: .carta-di-prova)")
        parser.add_argument("--senza-env", action="store_true", help="non aggiungere la configurazione al file .env")

    def handle(self, utente, pin, cartella, senza_env, **options):
        if not settings.DEBUG:
            raise CommandError("La carta di prova si usa solo in un'installazione di prova (DJANGO_DEBUG=1).")
        if not re.fullmatch(r"\d{4,8}", pin):
            raise CommandError("Il PIN deve avere da 4 a 8 cifre.")
        user = get_user_model().objects.filter(username=utente).first()
        if user is None:
            raise CommandError(f"Utente «{utente}» inesistente.")
        if not user.has_perm("signatures.sign_with_cie"):
            raise CommandError(f"L'utente «{utente}» non ha il permesso di firmare con la CIE (medico o coordinatore).")
        if not CF_RE.fullmatch((user.fiscal_code or "").upper()):
            user.fiscal_code = TEST_FISCAL_CODE
            user.save(update_fields=["fiscal_code"])
            self.stdout.write(f"• All'utente «{utente}» mancava il codice fiscale: impostato quello fittizio {TEST_FISCAL_CODE}.")

        folder = Path(cartella) if cartella else Path(settings.BASE_DIR) / ".carta-di-prova"
        folder.mkdir(parents=True, exist_ok=True)
        root_cert, inter_cert, inter_key = self.test_ca(folder)

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = _name(c="IT", given=user.first_name[:64], surname=user.last_name[:64], serial="PROVA0000",
                        cn=user.fiscal_code.upper())
        cert = _certificate(subject, inter_cert.subject, key.public_key(), inter_key, ca=False, years=2)
        card = folder / f"carta-di-prova-{user.username}.p12"
        card.write_bytes(pkcs12.serialize_key_and_certificates(
            b"carta-di-prova", key, cert, [inter_cert, root_cert], serialization.BestAvailableEncryption(pin.encode())))
        card.with_suffix(".cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))

        if not senza_env:
            self.write_env(folder)
        self.stdout.write(self.style.SUCCESS(f"✔ Carta di prova per «{utente}» creata: {card}"))
        self.stdout.write(f"  PIN: {pin} · codice fiscale nel certificato: {user.fiscal_code.upper()}")
        self.stdout.write("  NON è una CIE e non ha valore legale: serve solo a provare il FASAS senza lettore.")
        self.stdout.write("Poi: riavvia il FASAS e avvia il Signer con l'opzione --carta-di-prova seguita dal percorso "
                          "del file .p12 (vedi docs/FIRMA_CIE.md, «Prova senza lettore»).")

    def test_ca(self, folder):
        """CA radice e intermedia di prova: create una volta e riusate per le carte degli altri utenti."""
        root_path, inter_path, inter_key_path = folder / "ca-radice.pem", folder / "ca-intermedia.pem", folder / "ca-intermedia.key"
        if root_path.exists() and inter_path.exists() and inter_key_path.exists():
            root = x509.load_pem_x509_certificate(root_path.read_bytes())
            inter = x509.load_pem_x509_certificate(inter_path.read_bytes())
            inter_key = serialization.load_pem_private_key(inter_key_path.read_bytes(), password=None)
            return root, inter, inter_key
        organization = f"FASAS – {TEST_MARKER} – NON È UNA CIE"
        root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        root_name = _name(c="IT", o=organization, cn="CA radice di prova FASAS")
        root = _certificate(root_name, root_name, root_key.public_key(), root_key, ca=True, years=10)
        inter_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        inter = _certificate(_name(c="IT", o=organization, cn="CA intermedia di prova FASAS"), root_name,
                             inter_key.public_key(), root_key, ca=True, years=8)
        _pem(root_path, [root])
        _pem(inter_path, [inter])
        _private(inter_key_path, inter_key)  # serve solo a emettere altre carte di prova
        return root, inter, inter_key

    def write_env(self, folder):
        env = Path(settings.BASE_DIR) / ".env"
        raw = env.read_bytes() if env.exists() else b""
        # come config/settings.py: PowerShell salva .env in UTF-16; lo si riscrive in UTF-8
        current = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        if "FASAS_CIE_TRUST_ROOTS" in current:
            self.stdout.write("• Il file .env contiene già FASAS_CIE_TRUST_ROOTS: lo lascio com'è. Per la carta di prova "
                              f"deve indicare {(folder / 'ca-radice.pem').resolve().as_posix()}")
            return
        lines = [
            "",
            "# Carta di prova FASAS (solo prova, NON usare in produzione: rimuovere queste righe)",
            f"FASAS_CIE_TRUST_ROOTS={(folder / 'ca-radice.pem').resolve().as_posix()}",
            f"FASAS_CIE_INTERMEDIATES={(folder / 'ca-intermedia.pem').resolve().as_posix()}",
            "FASAS_CIE_REVOCATION=off",
        ]
        separator = "\n" if current and not current.endswith("\n") else ""
        env.write_text(current + separator + "\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(f"• Configurazione aggiunta a {env}")
