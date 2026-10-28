from django.apps import AppConfig


class AppointmentsConfig(AppConfig):
    name = "fasas.appointments"
    verbose_name = "Appuntamenti sanitari"

    def ready(self):
        from fasas.audit.services import register

        from .models import Appointment

        register(Appointment, exclude={"reminded_day_before", "reminded_same_day"})
