from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.home, name="home"),
    path("modello.xlsx", views.template_download, name="template"),
    path("excel/", views.workbook_upload, name="workbook"),
    path("documenti/", views.documents_upload, name="documents"),
    path("<int:pk>/", views.batch_detail, name="batch"),
    path("<int:pk>/conferma/", views.batch_confirm, name="confirm"),
    path("<int:pk>/annulla/", views.batch_cancel, name="cancel"),
]
