"""Verifica la configurazione della firma: livello PAdES, marca temporale e collegamento al servizio CSC."""
import getpass

from django.conf import settings
from django.core.management.base import BaseCommand

from fasas.signatures import csc
from fasas.signatures.providers import SignatureError, signature_level, trust_roots


class Command(BaseCommand):
    help = "Controlla la configurazione della firma digitale (e, con --utente, l'accesso alla firma remota)."

    def add_arguments(self, parser):
        parser.add_argument("--utente", help="Utente presso il prestatore per provare accesso e lettura credenziali")

    def ok(self, text):
        self.stdout.write(self.style.SUCCESS(f"✔ {text}"))

    def ko(self, text):
        self.stdout.write(self.style.ERROR(f"✖ {text}"))

    def handle(self, utente=None, **options):
        try:
            self.ok(f"Livello firma: PAdES-{signature_level()}")
        except SignatureError as exc:
            self.ko(str(exc))
        if settings.FASAS_SIGNATURE_TSA_URL:
            self.ok(f"Marca temporale: {settings.FASAS_SIGNATURE_TSA_URL}")
        else:
            self.stdout.write("• Marca temporale non configurata: la data della firma è quella dichiarata dal server")
        try:
            roots = trust_roots()
            if roots:
                self.ok(f"Certificati radice attendibili: {len(roots)}")
        except OSError as exc:
            self.ko(f"FASAS_SIGNATURE_TRUST_ROOTS non leggibile: {exc}")

        if not settings.FASAS_CSC_SERVICE_URL:
            self.stdout.write("• Firma remota (CSC) non configurata: i medici possono usare solo il certificato .p12")
            return
        config = csc.CSCConfig.from_settings()

        async def probe():
            async with csc.session() as http:
                client = csc.CSCClient(config, http)
                info = await client.info()
                self.ok(f"Servizio CSC raggiungibile: {info.get('name', config.service_url)} "
                        f"(API {', '.join(info.get('specs', [])) or config.api_version})")
                if info.get("authType"):
                    self.stdout.write(f"  metodi di accesso offerti: {', '.join(info['authType'])}")
                if not utente and config.needs_user_password:
                    return
                password = getpass.getpass("Password del servizio di firma: ") if config.needs_user_password else ""
                token = await client.access_token(utente or "", password)
                ids = await client.list_credentials(token, utente or "")
                self.ok(f"Accesso riuscito: {len(ids)} credenziali di firma")
                for credential_id in ids:
                    remote, _ = await client.credential_info(token, credential_id)
                    state = "utilizzabile" if remote.usable else f"NON utilizzabile ({remote.problem})"
                    unlock = " + ".join(x for x in ("PIN" if remote.pin_required else "",
                                                     f"OTP {remote.otp_type}" if remote.otp_type else "") if x)
                    self.stdout.write(f"  {credential_id}: {remote.subject} · {unlock or 'nessuno sblocco'} · {state}")

        try:
            csc.run(probe())
        except SignatureError as exc:
            self.ko(str(exc))
