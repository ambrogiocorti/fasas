from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "fasas.billing"
    verbose_name = "Presenze e rette"

    def ready(self):
        from fasas.audit.services import register

        from . import models

        register(models.BillingSettings, guest_field=None)
        register(models.AttendanceCorrection)
        register(models.AttendanceMonth, guest_field=None)
        register(models.GuestFeeLine)
        register(models.FeeStatement, exclude={"lines"})
        register(models.FeePayment, guest_field="statement__guest")
