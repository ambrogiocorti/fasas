from django.urls import path

from . import views

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
]
