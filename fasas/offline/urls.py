from django.urls import path

from . import views

app_name = "offline"

urlpatterns = [
    path("", views.offline_page, name="page"),
    path("stato/", views.status, name="status"),
    path("pacchetto/", views.pack, name="pack"),
    path("sincronizza/", views.sync_view, name="sync"),
    path("foglio-emergenza.pdf", views.emergency_pdf, name="emergency"),
    path("registrazioni/", views.records, name="records"),
]
