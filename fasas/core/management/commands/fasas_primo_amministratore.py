"""
Primo amministratore senza riga di comando (versione cloud, dove spesso non c'è un terminale sul server):
lo crea da FASAS_ADMIN_USERNAME e FASAS_ADMIN_PASSWORD solo se non esiste ancora nessun amministratore attivo.
Al primo accesso il FASAS chiede di attivare la verifica in due passaggi; poi la password va tolta dalle variabili.
"""
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from config.settings import env_secret
from fasas.accounts.models import Role
from fasas.audit.context import audit_context


class Command(BaseCommand):
    help = "Crea il primo amministratore da FASAS_ADMIN_USERNAME e FASAS_ADMIN_PASSWORD, se non ce n'è nessuno"

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("FASAS_ADMIN_USERNAME", "").strip()
        password = env_secret("FASAS_ADMIN_PASSWORD")
        if User.objects.filter(Q(is_superuser=True) | Q(role=Role.ADMIN), is_active=True).exists():
            if password:
                self.stdout.write(self.style.WARNING(
                    "Esiste già un amministratore: togliere FASAS_ADMIN_PASSWORD dalle variabili del servizio."))
            return
        if not username or not password:
            self.stdout.write(self.style.WARNING(
                "Nessun amministratore: impostare FASAS_ADMIN_USERNAME e FASAS_ADMIN_PASSWORD e riavviare."))
            return
        if User.objects.filter(username=username).exists():
            raise CommandError(f"L'utente {username} esiste già ma non è amministratore attivo: correggere a mano.")
        candidate = User(username=username, role=Role.ADMIN)
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise CommandError("FASAS_ADMIN_PASSWORD non accettata: " + " ".join(exc.messages)) from exc
        with audit_context(source="comando:primo_admin"):
            User.objects.create_superuser(username=username, email=os.environ.get("FASAS_ADMIN_EMAIL", "").strip(),
                                          password=password, role=Role.ADMIN)
        self.stdout.write(self.style.SUCCESS(
            f"Amministratore {username} creato. Dopo il primo accesso togliere FASAS_ADMIN_PASSWORD dalle variabili."))
