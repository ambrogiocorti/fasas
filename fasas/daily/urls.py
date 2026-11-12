from django.urls import path

from fasas.core.crud import config_urls

from . import views
from .forms import ChecklistItemForm, ChecklistTemplateForm
from .models import ChecklistItem, ChecklistTemplate

app_name = "daily"

urlpatterns = [
    path("registro/", views.shift_register, name="register"),
    path("evacuazioni/", views.evacuation_overview, name="evacuations"),
    path("evacuazioni/<int:guest_pk>/rapida/", views.evacuation_quick, name="evacuation_quick"),
    path("checklist/", views.checklist, name="checklist"),
    path("checklist/spunta/", views.checklist_toggle, name="checklist_toggle"),
    path("turni/", views.shift_roster, name="roster"),
    path("turni/presa-servizio/", views.check_in, name="check_in"),
    path("chiusure/", views.closures, name="closures"),
    path("chiusure/chiudi/", views.close_shift_view, name="close_shift"),
    path("chiusure/<int:pk>/", views.closure_detail, name="closure_detail"),

    path("ospite/<int:guest_pk>/", views.guest_daily, name="guest_daily"),
    path("ospite/<int:guest_pk>/nuova/", views.DailyRecordCreateView.as_view(), name="record_create"),
    path("registrazione/<int:pk>/modifica/", views.DailyRecordUpdateView.as_view(), name="record_update"),
    path("registrazione/<int:pk>/annulla/", views.DailyRecordVoidView.as_view(), name="record_void"),
    path("ospite/<int:guest_pk>/evacuazione/", views.EvacuationCreateView.as_view(), name="evacuation_create"),
    path("evacuazione/<int:pk>/modifica/", views.EvacuationUpdateView.as_view(), name="evacuation_update"),
    path("evacuazione/<int:pk>/annulla/", views.EvacuationVoidView.as_view(), name="evacuation_void"),
    path("ospite/<int:guest_pk>/diario/", views.guest_diary, name="guest_diary"),
    path("ospite/<int:guest_pk>/diario/nuova/", views.DiaryCreateView.as_view(), name="diary_create"),
    path("diario/<int:pk>/modifica/", views.DiaryUpdateView.as_view(), name="diary_update"),
    path("diario/<int:pk>/annulla/", views.DiaryVoidView.as_view(), name="diary_void"),
] + config_urls(
    "checklist-modelli", "checklisttemplate", ChecklistTemplate, ChecklistTemplateForm, ("name", "shift", "active"),
    namespace="daily",
) + config_urls(
    "checklist-voci", "checklistitem", ChecklistItem, ChecklistItemForm,
    ("template", "label", "check_type", "per_guest", "order"), namespace="daily",
    queryset=ChecklistItem.objects.select_related("template").order_by("template__shift", "order"),
)
