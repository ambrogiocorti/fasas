"""
Controllo dell'avvio di prova (avvia.sh, avvia.bat): l'installazione di prova usa chiavi di cifratura pubbliche e
utenti con password scritte nel README, quindi non parte se nel database ci sono ospiti diversi da quelli
dimostrativi, salvo conferma esplicita che sono tutti inventati.
"""
import sys

from django.core.management.base import BaseCommand, CommandError

CONFIRM = "DATI DI FANTASIA"


class Command(BaseCommand):
    help = "Prima dell'avvio di prova: rifiuta i database con ospiti veri (chiavi pubbliche, password note)."

    def add_arguments(self, parser):
        parser.add_argument("--conferma-dati-di-fantasia", action="store_true",
                            help="Conferma senza domanda che gli ospiti sono inventati (prove automatiche)")

    def handle(self, *args, **options):
        from fasas.guests.models import Guest

        from .fasas_demo import GUESTS

        others = Guest.objects.exclude(fiscal_code__in=[g[4] for g in GUESTS]).count()
        if not others:
            self.stdout.write("Avvio di prova: nel database ci sono solo gli ospiti dimostrativi.")
            return
        self.stderr.write(
            f"ATTENZIONE: nel database ci sono {others} ospiti che non sono quelli dimostrativi.\n"
            "L'avvio di prova usa chiavi di cifratura pubbliche e utenti con password scritte nel README:\n"
            "NON va usato con i dati di persone reali. Per l'uso vero: docs/INSTALLAZIONE_IN_STRUTTURA.md.")
        if options["conferma_dati_di_fantasia"]:
            return
        if not sys.stdin.isatty():
            raise CommandError("Avvio di prova annullato.")
        answer = input(f"Se TUTTI questi ospiti sono inventati scrivi «{CONFIRM}» e premi Invio: ")
        if answer.strip().upper() != CONFIRM:
            raise CommandError("Avvio di prova annullato.")
