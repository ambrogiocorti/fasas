"""
Carica l'elenco ufficiale delle confezioni di medicinali (open data AIFA, CSV o Excel) per compilare i farmaci e
riconoscere le confezioni con il lettore di codici a barre.

    python manage.py fasas_farmaci_aifa confezioni.csv
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fasas.audit.context import audit_context
from fasas.pharmacy.official import OfficialListError, import_list


class Command(BaseCommand):
    help = "Carica l'elenco ufficiale dei medicinali (open data AIFA) da un file CSV o Excel."

    def add_arguments(self, parser):
        parser.add_argument("file")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"File non trovato: {path}")
        try:
            with audit_context(user=None, ip="", reason="", source="comando fasas_farmaci_aifa"):
                record = import_list(path.read_bytes(), path.name)
        except OfficialListError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{record.packages} confezioni caricate ({record.skipped} righe scartate). "
                                             "Fonte: AIFA, licenza CC BY 4.0."))
