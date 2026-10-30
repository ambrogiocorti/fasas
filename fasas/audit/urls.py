from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.AuditLogListView.as_view(), name="list"),
    path("<int:pk>/", views.AuditLogDetailView.as_view(), name="detail"),
    path("verifica/", views.verify_view, name="verify"),
    path("punti-di-controllo/", views.checkpoint_list, name="checkpoints"),
    path("punti-di-controllo/<int:pk>/ricevuta/", views.checkpoint_receipt, name="checkpoint_receipt"),
]
