from django.urls import path

from . import credential_views, views

app_name = "staffing"

urlpatterns = [
    path("", views.rota, name="rota"),
    path("salva/", views.save_changes, name="save"),
    path("ripeti/", views.repeat, name="repeat"),
    path("pubblica/", views.publish_view, name="publish"),
    path("excel/", views.rota_excel, name="excel"),
    path("miei/", views.my_rota, name="my"),
    path("richieste/", views.requests_view, name="requests"),
    path("ferie/<int:pk>/decidi/", views.decide_leave_view, name="decide_leave"),
    path("ferie/<int:pk>/ritira/", views.cancel_leave, name="cancel_leave"),
    path("cambio/<int:pk>/rispondi/", views.respond_change_view, name="respond_change"),
    path("cambio/<int:pk>/decidi/", views.decide_change_view, name="decide_change"),
    path("regole/", views.settings_view, name="settings"),
    path("scadenze/", credential_views.overview, name="credentials"),
    path("scadenze/nuova/", credential_views.create, name="credential_create"),
    path("scadenze/mie/", credential_views.mine, name="my_credentials"),
    path("scadenze/dipendente/<int:user_pk>/", credential_views.user_view, name="credential_user"),
    path("scadenze/<int:pk>/attestato/", credential_views.certificate, name="credential_file"),
    path("scadenze/<int:pk>/elimina/", credential_views.delete, name="credential_delete"),
    path("scadenze/tipi/", credential_views.types, name="credential_types"),
    path("scadenze/tipi/nuovo/", credential_views.type_edit, name="credential_type_create"),
    path("scadenze/tipi/<int:pk>/", credential_views.type_edit, name="credential_type_update"),
]
