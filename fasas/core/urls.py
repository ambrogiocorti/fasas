from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("configurazione/", views.system_config, name="config"),
    path("impostazioni/", views.settings_hub, name="settings"),
    path("salute/", views.health, name="health"),
]
