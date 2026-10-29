"""Carica nelle cartelle degli ospiti una cartella di documenti scansionati (anche migliaia di file)."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fasas.documents.models import Document
from fasas.imports import documents as document_import
from fasas.imports.services import parse_date_arg

from ._common import get_user


class Command(BaseCommand):
    help = ("Abbina i file di una cartella agli ospiti (codice fiscale o «Cognome Nome» nel percorso) "
            "e con --conferma li carica come documenti cifrati.")

    def add_arguments(self, parser):
        parser.add_argument("cartella")
        parser.add_argument("--utente", required=True)
        parser.add_argument("--categoria", default=Document.Category.OTHER, choices=Document.Category.values)
        parser.add_argument("--data", help="Data dei documenti GG/MM/AAAA (facoltativa)")
        parser.add_argument("--conferma", action="store_true", help="Carica davvero (senza: solo abbinamento)")

    def handle(self, cartella, utente, categoria, data, conferma, **options):
        folder = Path(cartella)
        if not folder.is_dir():
            raise CommandError(f"Cartella non trovata: {folder}")
        user = get_user(utente)
        batch = document_import.prepare_from_folder(str(folder), user, categoria, parse_date_arg(data))
        matched = 0
        for entry in batch.payload:
            if entry["problem"]:
                self.stdout.write(f"SCARTATO  {entry['path']}: {entry['problem']}")
            elif entry["guest_id"]:
                matched += 1
                self.stdout.write(f"ok        {entry['path']} → ospite #{entry['guest_id']} «{entry['title']}»")
            else:
                self.stdout.write(f"NON ABBINATO {entry['path']}")
        if not conferma:
            document_import.cancel_batch(batch)
            self.stdout.write(self.style.WARNING(f"{matched} file abbinati su {len(batch.payload)}. "
                                                 "Rilanciare con --conferma per caricarli."))
            return
        created, skipped = document_import.confirm_batch(batch, user)
        self.stdout.write(self.style.SUCCESS(f"{created} documenti caricati, {skipped} scartati."))
