from django.core.management.base import BaseCommand, CommandError

from fasas.audit.context import audit_context
from fasas.backups.models import BackupRecord
from fasas.backups.services import create_backup, verify_backup


class Command(BaseCommand):
    help = "Crea un backup cifrato del database e dei file, poi ne verifica l'integrità"

    def add_arguments(self, parser):
        parser.add_argument("--no-media", action="store_true", help="Esclude i file caricati")

    def handle(self, *args, **options):
        with audit_context(source="cli"):
            record = create_backup(BackupRecord.Kind.MANUAL, include_media=not options["no_media"])
            if record.status != BackupRecord.Status.OK:
                raise CommandError(record.error)
            ok = verify_backup(record)
        self.stdout.write(self.style.SUCCESS(f"Backup {record.filename} ({record.size} byte) verifica={'OK' if ok else 'KO'}"))
