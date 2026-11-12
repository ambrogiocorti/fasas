from django.urls import path

from fasas.core.crud import config_urls

from . import views
from .forms import ReportScheduleForm, ReportTemplateForm
from .models import ReportSchedule, ReportTemplate

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("<int:pk>/scarica/", views.report_download, name="download"),
    path("ospite/<int:guest_pk>/cartella/", views.guest_export, name="guest_export"),
    path("ispezione/", views.inspection, name="inspection"),
    path("indicatori-qualita/", views.quality, name="quality"),
] + config_urls(
    "programmati", "schedule", ReportSchedule, ReportScheduleForm,
    ("name", "report_type", "template", "format", "frequency", "interval_days", "guest", "retention_years", "active",
     "last_run_at"),
    namespace="reports",
) + config_urls(
    "modelli", "template", ReportTemplate, ReportTemplateForm, ("name", "description", "sections_display"),
    namespace="reports",
)
