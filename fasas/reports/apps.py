from django.apps import AppConfig


class ReportsConfig(AppConfig):
    name = "fasas.reports"
    verbose_name = "Report ed esportazioni"

    def ready(self):
        from fasas.audit.services import register

        from .models import ReportSchedule

        register(ReportSchedule)
