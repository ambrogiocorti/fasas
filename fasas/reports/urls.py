from django.urls import path

from fasas.core.crud import config_urls

from . import views
from .forms import ReportScheduleForm
from .models import ReportSchedule

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("<int:pk>/scarica/", views.report_download, name="download"),
    path("ospite/<int:guest_pk>/cartella/", views.guest_export, name="guest_export"),
] + config_urls(
    "programmati", "schedule", ReportSchedule, ReportScheduleForm,
    ("name", "report_type", "format", "frequency", "guest", "retention_years", "active", "last_run_at"),
    namespace="reports",
)
