from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key

from fasas.backups.crypto import generate_key as backup_key
from fasas.core.encryption import generate_key as file_key


class Command(BaseCommand):
    help = "Genera chiavi nuove per .env (segreto Django, cifratura file, cifratura backup)"

    def handle(self, *args, **options):
        self.stdout.write(f"DJANGO_SECRET_KEY={get_random_secret_key()}")
        self.stdout.write(f"FASAS_ENCRYPTION_KEYS={file_key()}")
        self.stdout.write(f"FASAS_BACKUP_KEY={backup_key()}")
        self.stderr.write("Conservare FASAS_ENCRYPTION_KEYS e FASAS_BACKUP_KEY anche fuori dal server: "
                          "senza di esse documenti e backup non sono recuperabili.")
