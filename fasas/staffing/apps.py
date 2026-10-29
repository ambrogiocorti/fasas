from django.apps import AppConfig


class StaffingConfig(AppConfig):
    name = "fasas.staffing"
    verbose_name = "Turni del personale"

    def ready(self):
        from fasas.audit.services import register

        from . import models

        for model in (models.RotaSettings, models.StaffProfile, models.RotaMonth, models.RotaEntry,
                      models.LeaveRequest, models.ShiftChange):
            register(model, guest_field=None)
