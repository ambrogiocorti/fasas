from django.apps import AppConfig


class DailyConfig(AppConfig):
    name = "fasas.daily"
    verbose_name = "Registro giornaliero e turni"

    def ready(self):
        from django.db.models.signals import post_save

        from fasas.audit.services import register

        from . import models, receivers

        for model in (models.DailyRecord, models.EvacuationRecord, models.DiaryEntry, models.ChecklistCheck):
            register(model)
        for model in (models.ShiftAssignment, models.ChecklistTemplate, models.ChecklistItem):
            register(model, guest_field=None)
        post_save.connect(receivers.evacuation_saved, sender=models.EvacuationRecord, dispatch_uid="fasas-evac-saved")
