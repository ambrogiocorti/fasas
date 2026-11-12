from django.urls import path

from . import views

app_name = "modulistica"

urlpatterns = [
    path("", views.index, name="index"),
    path("intestazione/", views.settings_view, name="settings"),
    path("nuovo/", views.edit, name="create"),
    path("<int:pk>/", views.edit, name="edit"),
    path("<int:pk>/stato/<str:status>/", views.set_status, name="set_status"),
    path("<int:pk>/ripristina/", views.restore, name="restore"),
    path("<int:pk>/anteprima/", views.preview, name="preview"),
    path("<int:pk>/pdf/", views.blank_pdf, name="blank_pdf"),
    path("<int:pk>/distribuisci/", views.distribute, name="distribute"),
    path("miei/", views.mine, name="mine"),
    path("miei/<int:pk>/", views.fill_assignment, name="fill"),
    path("ospiti/", views.overview, name="overview"),
    path("ospite/<int:guest_pk>/", views.guest_view, name="guest"),
    path("ospite/<int:guest_pk>/<int:template_pk>/", views.guest_fill, name="guest_fill"),
    path("compilato/<int:pk>/pdf/", views.submission_pdf, name="submission_pdf"),
    path("compilato/<int:pk>/firmato/", views.submission_pdf, {"signed": True}, name="signed_pdf"),
    path("compilato/<int:pk>/carica-firmato/", views.signed_upload, name="signed_upload"),
    path("compilato/<int:pk>/revoca/", views.withdraw_view, name="withdraw"),
    path("famiglia/<int:link_pk>/<int:template_pk>/", views.family_fill, name="family_fill"),
    path("famiglia/<int:link_pk>/compilato/<int:pk>/", views.family_pdf, name="family_pdf"),
]
