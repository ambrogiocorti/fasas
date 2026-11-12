from django.core.management.base import BaseCommand, CommandError

from fasas.backups.models import RestoreTest
from fasas.backups.restore_test import run_restore_test


class Command(BaseCommand):
    help = ("Prova di ripristino con verbale: riapre l'ultimo backup (fuori sede se configurato) in un database "
            "separato e verifica l'audit log. Non tocca il database in uso.")

    def handle(self, *args, **options):
        test = run_restore_test()
        for step in test.steps:
            self.stdout.write(f"- {step}")
        for table, count in test.counts.items():
            self.stdout.write(f"  {table}: {count}")
        if test.result == RestoreTest.Result.FAILED:
            raise CommandError(f"Prova di ripristino FALLITA (verbale n. {test.pk}).")
        style = self.style.SUCCESS if test.result == RestoreTest.Result.OK else self.style.WARNING
        self.stdout.write(style(f"Prova di ripristino {test.get_result_display().lower()} (verbale n. {test.pk}, "
                                f"{test.duration_seconds} s)."))
