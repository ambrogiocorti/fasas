from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from fasas.backups.continuity import ContinuityError, copies, restore_latest
from fasas.backups.services import BackupError


class Command(BaseCommand):
    help = (
        "Ripristina il FASAS dal disco di continuità: l'ultima copia del database (al massimo pochi minuti prima "
        "del guasto) e i file. ATTENZIONE: sostituisce i dati attuali. Si usa su un server nuovo o riparato."
    )

    def add_arguments(self, parser):
        parser.add_argument("--cartella", help="Cartella del disco (default: FASAS_CONTINUITY_DIR)")
        parser.add_argument("--file", help="Nome di una copia precisa, invece dell'ultima")
        parser.add_argument("--elenca", action="store_true", help="Elenca le copie presenti, senza ripristinare")
        parser.add_argument("--confirm", action="store_true", help="Conferma esplicita del ripristino")
        parser.add_argument("--no-media", action="store_true")

    def handle(self, *args, **options):
        from pathlib import Path

        from fasas.backups.continuity import root

        try:
            base = Path(options["cartella"]) if options["cartella"] else root()
            if options["elenca"]:
                for moment, path in copies(base)[:50]:
                    self.stdout.write(f"{timezone.localtime(moment):%d/%m/%Y %H:%M:%S}  {path.name}")
                return
            if not options["confirm"]:
                raise CommandError("Aggiungere --confirm per confermare il ripristino.")
            moment, path = restore_latest(base, options["file"], restore_media=not options["no_media"])
        except (ContinuityError, BackupError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Ripristino completato dalla copia del {timezone.localtime(moment):%d/%m/%Y %H:%M} ({path.name}). "
            "Eseguire ora: python manage.py audit_verify"
        ))
