from django.apps import AppConfig


class SignaturesConfig(AppConfig):
    name = "fasas.signatures"
    verbose_name = "Firma digitale"

    def ready(self):
        from fasas.audit.services import register

        from .models import SigningCredential

        register(SigningCredential, exclude={"storage_name"}, guest_field=None)
