from django.apps import AppConfig


class FamiliesConfig(AppConfig):
    name = "fasas.families"
    verbose_name = "Area familiari e tutori"

    def ready(self):
        from fasas.audit.services import register

        from .models import FamilyLink, FamilyMessage, SharedDocument, VisitRequest

        register(FamilyLink)
        register(FamilyMessage, guest_field="link__guest")
        register(VisitRequest, guest_field="link__guest")
        register(SharedDocument, guest_field="document__guest")
