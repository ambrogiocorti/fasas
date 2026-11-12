from django.apps import AppConfig


class PaiConfig(AppConfig):
    name = "fasas.pai"
    verbose_name = "Piano Assistenziale Individuale"

    def ready(self):
        from fasas.audit.services import register

        from .models import PAI, PAIGoal

        register(PAI)
        register(PAIGoal, guest_field="pai__guest")
