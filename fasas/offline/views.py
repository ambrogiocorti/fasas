import hashlib
import json

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.notifications import push

from .emergency import emergency_sheet
from .models import OfflineRecord
from .pack import build_pack
from .sync import sync

SHELL_STATIC = ["css/fasas.css", "js/fasas.js", "js/offline.js", "img/icon-192.png", "img/badge-96.png"]
PERM = "offline.use_offline"


def _version():
    """Cambia quando cambia l'involucro: il browser scarica allora il nuovo service worker."""
    digest = hashlib.sha256(settings.SECRET_KEY[:8].encode())
    for folder, names in ((settings.BASE_DIR / "static", SHELL_STATIC),
                          (settings.BASE_DIR / "templates", ["offline/page.html", "pwa/sw.js"])):
        for name in names:
            path = folder / name
            digest.update(f"{name}:{path.stat().st_mtime_ns if path.exists() else 0}".encode())
    return digest.hexdigest()[:12]


@never_cache
def service_worker(request):
    response = render(request, "pwa/sw.js", {
        "version": _version(), "offline_url": reverse("offline:page"),
        "shell": [static(name) for name in SHELL_STATIC],
        "icon_url": static("img/icon-192.png"), "badge_url": static("img/badge-96.png"),
    }, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    return response


def manifest(request):
    name = getattr(request, "fasas_config", None)
    community = name.community.name if name else "FASAS"
    data = {
        "name": f"FASAS Digitale – {community}", "short_name": "FASAS", "lang": "it", "dir": "ltr",
        "start_url": "/", "scope": "/", "display": "standalone", "background_color": "#f3f5f8",
        "theme_color": "#1d5fa0", "description": "Fascicolo Socio Assistenziale Sanitario",
        "icons": [
            {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("img/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/manifest+json")


def offline_page(request):
    """Involucro della modalità offline: nessun dato nella pagina, tutto arriva dal pacchetto cifrato."""
    return render(request, "offline/page.html", {
        "status_url": reverse("offline:status"), "pack_url": reverse("offline:pack"), "sync_url": reverse("offline:sync"),
        "login_url": reverse(settings.LOGIN_URL) + "?next=" + reverse("offline:page"),
    })


@never_cache
def status(request):
    """Usato dalla pagina offline per capire se la rete è tornata e se l'utente ha una sessione valida."""
    if not request.user.is_authenticated:
        return JsonResponse({"online": True, "authenticated": False}, status=401)
    return JsonResponse({
        "online": True, "authenticated": True, "user": request.user.username, "csrf": get_token(request),
        "can_use_offline": request.user.has_perm(PERM), "server_time": timezone.now().isoformat(),
    })


@never_cache
def pack(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login"}, status=401)
    if not request.user.has_perm(PERM):
        return JsonResponse({"error": "forbidden"}, status=403)
    data = build_pack(request.user)
    log_event(AuditLog.Action.DOWNLOAD, None, user=request.user, repr_text="Pacchetto dati per lavoro senza rete",
              changes={"ospiti": [None, len(data["guests"])]}, reason="Aggiornamento dati del turno sul dispositivo")
    response = JsonResponse(data)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def sync_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login"}, status=401)
    if not request.user.has_perm(PERM):
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        body = json.loads(request.body)
        records = body["records"]
        if not isinstance(records, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("Richiesta non valida")
    if body.get("user") and body["user"] != request.user.username:
        return JsonResponse({"error": "user_mismatch"}, status=409)
    return JsonResponse({"results": sync(request.user, records)})


@permission_required(PERM, raise_exception=True)
def emergency_pdf(request):
    data = emergency_sheet(request.user)
    log_event(AuditLog.Action.EXPORT, None, user=request.user, repr_text="Foglio di emergenza",
              changes={"foglio di emergenza": [None, "PDF"]}, reason="Stampa del foglio di emergenza")
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(
        False, f"foglio-emergenza-{timezone.localdate():%Y-%m-%d}.pdf")
    response["Cache-Control"] = "no-store"
    return response


@permission_required(PERM, raise_exception=True)
def records(request):
    """Preparazione al lavoro senza rete e registrazioni sincronizzate (tutte per il coordinatore, le proprie per gli altri)."""
    qs = OfflineRecord.objects.select_related("user", "guest")
    see_all = request.user.has_perm("offline.view_offlinerecord")
    if not see_all:
        qs = qs.filter(user=request.user)
    if request.GET.get("problems"):
        qs = qs.exclude(status=OfflineRecord.Status.OK)
    return render(request, "offline/records.html", {
        "records": qs[:300], "see_all": see_all, "problems": qs.exclude(status=OfflineRecord.Status.OK).count()
        if not request.GET.get("problems") else None, "push_enabled": push.is_enabled(),
    })
