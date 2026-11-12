from django.apps import AppConfig


class CareConfig(AppConfig):
    name = "fasas.care"
    verbose_name = "Attività assistenziali a orario"

    def ready(self):
        from fasas.audit.services import register

        from .models import CareTask, CareTaskCheck

        register(CareTask)
        register(CareTaskCheck)
