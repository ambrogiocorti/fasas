from django.apps import AppConfig


class PharmacyConfig(AppConfig):
    name = "fasas.pharmacy"
    verbose_name = "Farmaci e magazzino"

    def ready(self):
        from fasas.audit.services import register

        from .models import Drug, DrugInteraction, StockLot

        register(Drug, guest_field=None)
        register(DrugInteraction, guest_field=None)
        register(StockLot)
