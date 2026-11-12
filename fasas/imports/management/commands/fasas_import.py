"""Importa il modello Excel compilato dalla riga di comando (utile per file grandi o prove ripetute)."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fasas.imports.services import run_workbook_import

from ._common import get_user


class Command(BaseCommand):
    help = "Controlla (e con --conferma importa) un file Excel compilato sul modello di importazione."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Percorso del file .xlsx")
        parser.add_argument("--utente", required=True, help="Utente a cui attribuire l'importazione nell'audit log")
        parser.add_argument("--conferma", action="store_true", help="Importa davvero (senza: solo anteprima)")

    def handle(self, file, utente, conferma, **options):
        path = Path(file)
        if not path.is_file():
            raise CommandError(f"File non trovato: {path}")
        user = get_user(utente)
        report = run_workbook_import(path.read_bytes(), user, commit=conferma, filename=path.name)
        for sheet, counts in report.counts.items():
            if counts["created"] or counts["skipped"]:
                verb = "inserite" if report.committed else "da inserire"
                self.stdout.write(f"{sheet}: {counts['created']} {verb}, {counts['skipped']} già presenti")
        for issue in report.issues:
            prefix = "ERRORE " if issue.level == "error" else "avviso "
            where = f"{issue.sheet} riga {issue.row}" + (f", {issue.column}" if issue.column else "")
            self.stdout.write(f"{prefix}{where}: {issue.message}")
        if report.errors:
            raise CommandError(f"{len(report.errors)} errori: nessun dato importato.")
        if report.committed:
            self.stdout.write(self.style.SUCCESS(f"Importazione completata: {report.total_created} voci."))
        else:
            self.stdout.write(self.style.WARNING("Anteprima senza errori. Rilanciare con --conferma per importare."))
