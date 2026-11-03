from django.apps import AppConfig


class AssessmentsConfig(AppConfig):
    name = "fasas.assessments"
    verbose_name = "Scale di valutazione"

    def ready(self):
        from fasas.audit.services import register

        from .models import Assessment, ScaleSetting

        register(Assessment)
        register(ScaleSetting, guest_field=None)
