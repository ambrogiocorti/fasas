from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "FASAS Digitale – amministrazione tecnica"
admin.site.site_title = "FASAS"

urlpatterns = [
    path("", include("fasas.core.urls")),
    path("", include("fasas.accounts.urls")),
    path("ospiti/", include("fasas.guests.urls")),
    path("sanitario/", include("fasas.clinical.urls")),
    path("giornaliero/", include("fasas.daily.urls")),
    path("magazzino/", include("fasas.pharmacy.urls")),
    path("documenti/", include("fasas.documents.urls")),
    path("firma/", include("fasas.signatures.urls")),
    path("protocolli/", include("fasas.protocols.urls")),
    path("appuntamenti/", include("fasas.appointments.urls")),
    path("pai/", include("fasas.pai.urls")),
    path("notifiche/", include("fasas.notifications.urls")),
    path("report/", include("fasas.reports.urls")),
    path("backup/", include("fasas.backups.urls")),
    path("audit/", include("fasas.audit.urls")),
    path("cerca/", include("fasas.search.urls")),
    path("api/", include("fasas.api.urls")),
    path("gestione-tecnica/", admin.site.urls),
]
