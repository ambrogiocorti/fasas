from django.urls import path

from fasas.core.crud import config_urls

from . import views
from .forms import ParameterTypeForm
from .models import ParameterType

app_name = "clinical"

urlpatterns = [
    path("giro-farmaci/", views.administration_board, name="board"),
    path("terapie/", views.therapy_overview, name="therapy_overview"),
    path("terapia/<int:therapy_pk>/somministra/", views.administer, name="administer"),
    path("sos/da-validare/", views.sos_pending, name="sos_pending"),
    path("sos/<int:pk>/valida/", views.sos_validate, name="sos_validate"),
    path("emergenza/", views.emergency, name="emergency"),

    path("ospite/<int:guest_pk>/terapie/", views.guest_therapies, name="guest_therapies"),
    path("ospite/<int:guest_pk>/terapie/nuova/", views.TherapyCreateView.as_view(), name="therapy_create"),
    path("ospite/<int:guest_pk>/sos/", views.sos_administer, name="sos_administer"),
    path("ospite/<int:guest_pk>/somministrazioni/", views.guest_administrations, name="guest_administrations"),
    path("terapia/<int:pk>/", views.TherapyDetailView.as_view(), name="therapy_detail"),
    path("terapia/<int:pk>/modifica/", views.TherapyUpdateView.as_view(), name="therapy_update"),
    path("terapia/<int:pk>/stato/", views.therapy_status, name="therapy_status"),
    path("somministrazione/<int:pk>/annulla/", views.administration_void, name="administration_void"),

    path("ospite/<int:guest_pk>/parametri/", views.guest_parameters, name="guest_parameters"),
    path("ospite/<int:guest_pk>/parametri/nuovo/", views.ParameterCreateView.as_view(), name="parameter_create"),
    path("ospite/<int:guest_pk>/parametri/rapido/", views.quick_parameters, name="quick_parameters"),
    path("parametro/<int:pk>/modifica/", views.ParameterUpdateView.as_view(), name="parameter_update"),
    path("parametro/<int:pk>/annulla/", views.ParameterVoidView.as_view(), name="parameter_void"),

    path("ospite/<int:guest_pk>/eventi/", views.guest_events, name="guest_events"),
    path("ospite/<int:guest_pk>/eventi/nuovo/", views.EventCreateView.as_view(), name="event_create"),
    path("evento/<int:pk>/", views.EventDetailView.as_view(), name="event_detail"),
    path("evento/<int:pk>/modifica/", views.EventUpdateView.as_view(), name="event_update"),
    path("evento/<int:pk>/annulla/", views.EventVoidView.as_view(), name="event_void"),

    path("ospite/<int:guest_pk>/contenzioni/nuova/", views.RestraintCreateView.as_view(), name="restraint_create"),
    path("contenzione/<int:pk>/modifica/", views.RestraintUpdateView.as_view(), name="restraint_update"),
    path("contenzione/<int:pk>/annulla/", views.RestraintVoidView.as_view(), name="restraint_void"),
] + config_urls(
    "tipi-parametro", "parametertype", ParameterType, ParameterTypeForm,
    ("name", "unit", "kind", "min_normal", "max_normal", "active"), namespace="clinical",
)
