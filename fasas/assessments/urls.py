from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("ospite/<int:guest_pk>/", views.guest_assessments, name="guest"),
    path("ospite/<int:guest_pk>/nuova/<slug:scale>/", views.assessment_create, name="create"),
    path("<int:pk>/", views.assessment_detail, name="detail"),
    path("<int:pk>/annulla/", views.AssessmentVoidView.as_view(), name="void"),
    path("da-fare/", views.due_overview, name="due"),
    path("impostazioni/", views.scale_settings, name="settings"),
]
