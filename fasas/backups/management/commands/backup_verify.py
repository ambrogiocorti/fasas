from django.core.management.base import BaseCommand, CommandError

from fasas.backups.models import BackupRecord
from fasas.backups.services import verify_backup


class Command(BaseCommand):
    help = "Verifica l'integrità di un backup (default: l'ultimo)"

    def add_arguments(self, parser):
        parser.add_argument("backup_id", nargs="?", type=int)

    def handle(self, *args, **options):
        qs = BackupRecord.objects.filter(status=BackupRecord.Status.OK, deleted_at__isnull=True)
        record = qs.filter(pk=options["backup_id"]).first() if options["backup_id"] else qs.first()
        if record is None:
            raise CommandError("Nessun backup trovato.")
        if not verify_backup(record):
            raise CommandError(record.error)
        self.stdout.write(self.style.SUCCESS(f"Backup {record.filename}: integrità verificata."))
