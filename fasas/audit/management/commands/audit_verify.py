from django.core.management.base import BaseCommand, CommandError

from fasas.audit.anchoring import check_previous_checkpoints, create_checkpoint, verify_timestamp
from fasas.audit.models import AuditCheckpoint
from fasas.audit.services import verify_chain


class Command(BaseCommand):
    help = ("Verifica la catena di hash dell'audit log, i punti di controllo e le loro marche temporali; "
            "con --salva registra anche un nuovo punto di controllo (come il job notturno)")

    def add_arguments(self, parser):
        parser.add_argument("--salva", action="store_true", help="Salva un punto di controllo con marca temporale")

    def handle(self, *args, **options):
        if options["salva"]:
            checkpoint = create_checkpoint("manuale")
            ok, count, broken = checkpoint.chain_ok, checkpoint.entries, checkpoint.broken_at
            rewritten = checkpoint.mismatched_checkpoints
        else:
            ok, count, broken = verify_chain()
            rewritten = [cp.pk for cp in check_previous_checkpoints()]
        bad_stamps = [cp.pk for cp in AuditCheckpoint.objects.exclude(timestamp_token=None)
                      if not verify_timestamp(cp.timestamp_token, cp.message())["intact"]]
        stamped = AuditCheckpoint.objects.exclude(timestamp_token=None).count()
        if broken:
            raise CommandError(f"Catena interrotta alla voce #{broken} (verificate {count} voci).")
        if rewritten:
            raise CommandError(f"Storia riscritta: i punti di controllo {rewritten} non corrispondono più all'audit log.")
        if bad_stamps:
            raise CommandError(f"Marche temporali non valide per i punti di controllo {bad_stamps}.")
        self.stdout.write(self.style.SUCCESS(
            f"Audit log integro: {count} voci verificate; {AuditCheckpoint.objects.count()} punti di controllo "
            f"coerenti, {stamped} con marca temporale integra."))
