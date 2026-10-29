"""Genera la chiave VAPID per le notifiche push (da mettere in FASAS_VAPID_PRIVATE_KEY, una volta sola)."""
from django.core.management.base import BaseCommand

from fasas.notifications import push


class Command(BaseCommand):
    help = "Genera la chiave privata VAPID per le notifiche push e mostra la chiave pubblica corrispondente."

    def handle(self, **options):
        private = push.generate_private_key()
        key = push.load_private_key(private)
        from cryptography.hazmat.primitives import serialization

        public = push._b64url(key.public_key().public_bytes(serialization.Encoding.X962,
                                                            serialization.PublicFormat.UncompressedPoint))
        self.stdout.write("Aggiungere al file .env del server (e conservarla: se cambia, ogni dispositivo va riattivato):\n")
        self.stdout.write(f"FASAS_VAPID_PRIVATE_KEY={private}")
        self.stdout.write(f"\nChiave pubblica (informativa): {public}")
