from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "fasas.documents"
    verbose_name = "Documenti"

    def ready(self):
        from fasas.audit.services import register

        from .models import Document

        register(Document)
