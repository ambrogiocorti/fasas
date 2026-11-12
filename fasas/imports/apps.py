from django.apps import AppConfig


class ImportsConfig(AppConfig):
    name = "fasas.imports"
    verbose_name = "Importazione dati"

    def ready(self):
        from fasas.audit.services import register

        from .models import ImportBatch

        register(ImportBatch, exclude={"payload", "summary"}, guest_field=None)
