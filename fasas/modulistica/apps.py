from django.apps import AppConfig


class ModulisticaConfig(AppConfig):
    name = "fasas.modulistica"
    verbose_name = "Modulistica"

    def ready(self):
        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_save

        from fasas.audit.services import register

        from . import models
        from .services import assign_new_user

        register(models.FormSettings, guest_field=None)
        register(models.FormTemplate, guest_field=None)
        register(models.FormField, guest_field=None)
        register(models.FormAssignment, guest_field=None)
        register(models.FormSubmission, exclude={"answers", "snapshot"})
        post_save.connect(assign_new_user, sender=get_user_model(), dispatch_uid="modulistica-new-user")
