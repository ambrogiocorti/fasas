from django.urls import path

from fasas.signatures import views as signature_views

from . import views

app_name = "documents"

urlpatterns = [
    path("da-firmare/", views.to_sign, name="to_sign"),
    path("ospite/<int:guest_pk>/", views.guest_documents, name="guest_list"),
    path("ospite/<int:guest_pk>/nuovo/", views.document_create, name="create"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/modifica/", views.document_edit, name="edit"),
    path("<int:pk>/versione/", views.version_upload, name="version_upload"),
    path("versione/<int:pk>/scarica/", views.version_download, name="download"),
    path("versione/<int:pk>/visualizza/", views.version_view, name="view"),
    path("versione/<int:pk>/firma/", signature_views.sign_version_view, name="sign"),
    path("versione/<int:pk>/firma-cie/", signature_views.cie_sign_view, name="sign_cie"),
    path("versione/<int:pk>/verifica-firma/", signature_views.verify_version_view, name="verify"),
]
