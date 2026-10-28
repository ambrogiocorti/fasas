from django.apps import AppConfig


class ProtocolsConfig(AppConfig):
    name = "fasas.protocols"
    verbose_name = "Protocolli automatici"

    def ready(self):
        from fasas.audit.services import register

        from .models import Protocol, ProtocolActionLog, ProtocolActivation

        register(Protocol, guest_field=None)
        register(ProtocolActivation)
        register(ProtocolActionLog, guest_field="activation__guest")
