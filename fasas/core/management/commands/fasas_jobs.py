from django.core.management.base import BaseCommand, CommandError

from fasas.core.jobs import JOBS, run_job


class Command(BaseCommand):
    help = "Esegue uno o più job periodici (alternativa a Celery beat, ad es. da cron)"

    def add_arguments(self, parser):
        parser.add_argument("jobs", nargs="*", help=f"Nomi dei job: {', '.join(JOBS)}; 'all' per tutti tranne il backup")
        parser.add_argument("--list", action="store_true", help="Elenca i job disponibili")

    def handle(self, *args, **options):
        if options["list"] or not options["jobs"]:
            for name, (_, description) in JOBS.items():
                self.stdout.write(f"{name:18} {description}")
            return
        names = [n for n in JOBS if n != "backup"] if options["jobs"] == ["all"] else options["jobs"]
        for name in names:
            if name not in JOBS:
                raise CommandError(f"Job sconosciuto: {name}")
            result = run_job(name)
            self.stdout.write(self.style.SUCCESS(f"{name}: {result}"))
