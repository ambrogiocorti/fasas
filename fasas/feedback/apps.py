from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    name = "fasas.feedback"
    verbose_name = "Segnalazioni e indicatori del pilota"

    def ready(self):
        from fasas.audit.services import register

        from . import models

        register(models.Feedback, guest_field=None)
