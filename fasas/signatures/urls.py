from django.urls import path

from . import views

app_name = "signatures"

urlpatterns = [
    path("credenziale/", views.credential_view, name="credential"),
    path("dispositivi/", views.devices_admin, name="devices"),
    path("cie/prova/", views.cie_test, name="cie_test"),
    path("cie/<uuid:request_id>/", views.cie_request_view, name="cie_request"),
    path("cie/<uuid:request_id>/stato/", views.cie_status, name="cie_status"),
    path("cie/<uuid:request_id>/annulla/", views.cie_cancel, name="cie_cancel"),
    path("cie/<uuid:request_id>/riprova/", views.cie_retry, name="cie_retry"),
    path("cie/<uuid:request_id>/file/", views.cie_test_file, name="cie_test_file"),
]
