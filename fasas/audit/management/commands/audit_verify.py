from django.core.management.base import BaseCommand, CommandError

from fasas.audit.services import verify_chain


class Command(BaseCommand):
    help = "Verifica l'integrità della catena di hash dell'audit log"

    def handle(self, *args, **options):
        ok, count, broken = verify_chain()
        if not ok:
            raise CommandError(f"Catena interrotta alla voce #{broken} (verificate {count} voci).")
        self.stdout.write(self.style.SUCCESS(f"Audit log integro: {count} voci verificate."))
