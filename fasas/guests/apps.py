from django.apps import AppConfig


class GuestsConfig(AppConfig):
    name = "fasas.guests"
    verbose_name = "Ospiti"

    def ready(self):
        from django.db.models.signals import m2m_changed

        from fasas.audit.services import register

        from . import models, receivers

        register(models.Guest)
        for model in (models.GuestContact, models.Diagnosis, models.Allergy, models.AdmissionEvent):
            register(model)
        register(models.ClinicalTag, guest_field=None)
        m2m_changed.connect(receivers.tags_changed, sender=models.Guest.tags.through, dispatch_uid="fasas-guest-tags")
