from django.urls import path

from fasas.core.crud import config_urls

from . import views
from .forms import ClinicalTagForm
from .models import ClinicalTag

app_name = "guests"

urlpatterns = [
    path("", views.guest_list, name="list"),
    path("nuovo/", views.GuestCreateView.as_view(), name="create"),
    path("<int:pk>/", views.guest_detail, name="detail"),
    path("<int:pk>/anagrafica/", views.GuestUpdateView.as_view(), name="update"),
    path("<int:pk>/sanitario/", views.guest_health, name="health"),
    path("<int:pk>/storico/", views.guest_timeline, name="timeline"),
    path("<int:pk>/dimissione/", views.guest_discharge, name="discharge"),
    path("<int:pk>/movimento/", views.guest_movement, name="movement"),
    path("<int:pk>/tag/<int:tag_pk>/", views.toggle_tag, name="toggle_tag"),
    path("<int:guest_pk>/contatti/nuovo/", views.contact_edit, name="contact_create"),
    path("<int:guest_pk>/contatti/<int:pk>/", views.contact_edit, name="contact_edit"),
    path("<int:guest_pk>/diagnosi/nuova/", views.diagnosis_edit, name="diagnosis_create"),
    path("<int:guest_pk>/diagnosi/<int:pk>/", views.diagnosis_edit, name="diagnosis_edit"),
    path("<int:guest_pk>/allergie/nuova/", views.allergy_edit, name="allergy_create"),
    path("<int:guest_pk>/allergie/<int:pk>/", views.allergy_edit, name="allergy_edit"),
] + config_urls("tag", "tag", ClinicalTag, ClinicalTagForm, ("name", "alert_message", "order"), namespace="guests")
