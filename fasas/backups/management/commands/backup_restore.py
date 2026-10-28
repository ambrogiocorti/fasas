from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from fasas.backups.services import BackupError, restore_backup


class Command(BaseCommand):
    help = (
        "Ripristina un backup cifrato. ATTENZIONE: sostituisce i dati attuali. "
        "Fermare l'applicazione prima di procedere. Per un backup JSON il database deve essere vuoto e migrato."
    )

    def add_arguments(self, parser):
        parser.add_argument("file", help="Percorso del file .fbk (o nome file nella cartella backup)")
        parser.add_argument("--confirm", action="store_true", help="Conferma esplicita del ripristino")
        parser.add_argument("--no-media", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("Aggiungere --confirm per confermare il ripristino.")
        path = Path(options["file"])
        if not path.is_absolute():
            path = settings.FASAS_BACKUP_DIR / path
        try:
            manifest = restore_backup(path, restore_media=not options["no_media"])
        except BackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Ripristino completato dal backup del {manifest['created_at']} ({manifest['db_format']}). "
            "Eseguire ora: python manage.py audit_verify"
        ))
