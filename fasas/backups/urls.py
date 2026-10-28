from django.urls import path

from . import views

app_name = "backups"

urlpatterns = [
    path("", views.backup_list, name="list"),
    path("esegui/", views.backup_run, name="run"),
    path("<int:pk>/verifica/", views.backup_verify, name="verify"),
    path("<int:pk>/scarica/", views.backup_download, name="download"),
]
