"""Pianificatore integrato dei job periodici (versione cloud, senza Redis né Celery). Vedi fasas/core/scheduler.py."""
import logging

from django.core.management.base import BaseCommand

from fasas.core.scheduler import SCHEDULE, Scheduler

logger = logging.getLogger("fasas.jobs")


class Command(BaseCommand):
    help = "Esegue i job periodici agli orari previsti (alternativa a Celery beat; si ferma con SIGTERM o Ctrl+C)"

    def add_arguments(self, parser):
        parser.add_argument("--una-volta", action="store_true", dest="once",
                            help="Un solo controllo (recupera i job dovuti nelle ultime 26 ore) e poi esce")
        parser.add_argument("--orari", action="store_true", dest="list", help="Elenca gli orari e esce")

    def handle(self, *args, **options):
        if options["list"]:
            for name, job, spec in SCHEDULE:
                when = " ".join(f"{key}={value}" for key, value in spec.items()) or "ogni minuto"
                self.stdout.write(f"{job:18} {when:45} {name}")
            return
        scheduler = Scheduler()
        if not options["once"]:
            scheduler.install_signals()
            logger.info("Pianificatore avviato: %d orari", len(SCHEDULE))
        scheduler.run(once=options["once"])
        if not options["once"]:
            logger.info("Pianificatore fermato")
