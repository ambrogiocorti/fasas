from django.apps import AppConfig


class ClinicalConfig(AppConfig):
    name = "fasas.clinical"
    verbose_name = "Cartella sanitaria"

    def ready(self):
        from django.db.models.signals import post_save

        from fasas.audit.services import register

        from . import models, receivers

        for model in (models.Therapy, models.TherapyAdministration, models.ParameterReading,
                      models.ClinicalEvent, models.Restraint):
            register(model)
        register(models.ParameterType, guest_field=None)
        post_save.connect(receivers.event_saved, sender=models.ClinicalEvent, dispatch_uid="fasas-event-saved")
        post_save.connect(receivers.parameter_saved, sender=models.ParameterReading, dispatch_uid="fasas-param-saved")
