from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import include, path

from fasas.offline import views as offline_views

admin.site.site_header = "FASAS Digitale – amministrazione tecnica"
admin.site.site_title = "FASAS"


def _admin_login(request, extra_context=None):
    """L'area tecnica non ha un accesso proprio: si entra dal login del FASAS, con la verifica in due passaggi."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return redirect_to_login(request.get_full_path())


admin.site.login = _admin_login

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
    path("importa/", include("fasas.imports.urls")),
    path("offline/", include("fasas.offline.urls")),
    path("amministrazione/", include("fasas.billing.urls")),
    path("turni/", include("fasas.staffing.urls")),
    path("sw.js", offline_views.service_worker, name="service_worker"),
    path("manifest.webmanifest", offline_views.manifest, name="manifest"),
    path("api/firma/v1/", include("fasas.signatures.api_urls")),
    path("api/", include("fasas.api.urls")),
    path("gestione-tecnica/", admin.site.urls),
]
