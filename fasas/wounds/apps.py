from django.apps import AppConfig


class WoundsConfig(AppConfig):
    name = "fasas.wounds"
    verbose_name = "Lesioni e medicazioni"

    def ready(self):
        from fasas.audit.services import register

        from .models import Dressing, DressingPlan, Wound, WoundCheck

        register(Wound)
        register(WoundCheck)
        register(Dressing)
        register(DressingPlan, guest_field="wound__guest")
