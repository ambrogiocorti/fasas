from django.apps import AppConfig


class PersonalConfig(AppConfig):
    name = "fasas.personal"
    verbose_name = "Denaro e oggetti personali degli ospiti"

    def ready(self):
        from fasas.audit.services import register

        from .models import CashMovement, PersonalItem

        register(CashMovement)
        register(PersonalItem)
