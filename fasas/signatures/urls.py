from django.urls import path

from . import views

app_name = "signatures"

urlpatterns = [
    path("credenziale/", views.credential_view, name="credential"),
]
