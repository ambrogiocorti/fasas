from django.urls import path

from . import api

app_name = "signer_api"

urlpatterns = [
    path("abbina/", api.pair, name="pair"),
    path("dispositivo/", api.me, name="me"),
    path("dispositivo/stato/", api.device_status, name="device_status"),
    path("dispositivo/chiave/", api.device_key, name="device_key"),
    path("richieste/", api.pending, name="pending"),
    path("richieste/<uuid:request_id>/prendi/", api.claim, name="claim"),
    path("richieste/<uuid:request_id>/stato/", api.state, name="state"),
    path("richieste/<uuid:request_id>/certificato/", api.certificate, name="certificate"),
    path("richieste/<uuid:request_id>/firma/", api.sign, name="sign"),
    path("richieste/<uuid:request_id>/conferma/", api.confirm, name="confirm"),
    path("richieste/<uuid:request_id>/errore/", api.error, name="error"),
]
