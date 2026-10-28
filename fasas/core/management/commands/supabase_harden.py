from django.core.management.base import BaseCommand
from django.db import connection

from fasas.core.supabase import harden


class Command(BaseCommand):
    help = "Attiva la RLS e revoca i privilegi ai ruoli API di Supabase (anon, authenticated) su tutte le tabelle"

    def handle(self, *args, **options):
        result = harden(connection)
        self.stdout.write(self.style.SUCCESS(f"Protezione applicata: {result}"))
