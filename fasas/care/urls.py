from django.urls import path

from . import views

app_name = "care"

urlpatterns = [
    path("", views.due, name="due"),
    path("fatta/", views.check_quick, name="check_quick"),
    path("esito/", views.check_form, name="check"),
    path("ospite/<int:guest_pk>/", views.guest_tasks, name="guest"),
    path("ospite/<int:guest_pk>/nuova/", views.task_create, name="create"),
    path("<int:pk>/modifica/", views.task_update, name="update"),
    path("<int:pk>/termina/", views.task_end, name="end"),
    path("registrazione/<int:pk>/annulla/", views.CheckVoidView.as_view(), name="check_void"),
]
