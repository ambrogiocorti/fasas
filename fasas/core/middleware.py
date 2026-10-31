import ipaddress
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from .models import Community, SystemConfig


def client_ip(request):
    """IP del client. X-Forwarded-For è considerato solo se ci sono proxy fidati configurati."""
    proxies = settings.FASAS_TRUSTED_PROXY_COUNT
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies and forwarded:
        chain = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(chain) >= proxies:
            return chain[-proxies]
    return request.META.get("REMOTE_ADDR", "")


class AllowedNetworksMiddleware:
    """Il sistema è accessibile solo dalle reti della comunità (FASAS_ALLOWED_NETWORKS)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = [ipaddress.ip_network(net, strict=False) for net in settings.FASAS_ALLOWED_NETWORKS]

    def __call__(self, request):
        if self.networks:
            try:
                ip = ipaddress.ip_address(client_ip(request))
            except ValueError:
                return HttpResponseForbidden("Accesso non consentito da questa rete.")
            if not any(ip in net for net in self.networks):
                return HttpResponseForbidden("Accesso non consentito da questa rete.")
        return self.get_response(request)


class CommunityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.community = SimpleLazyObject(Community.default)
        request.fasas_config = SimpleLazyObject(SystemConfig.get)
        return self.get_response(request)


class SessionIdleTimeoutMiddleware:
    """Disconnette dopo N minuti di inattività: i terminali di reparto sono condivisi."""

    PASSIVE_PREFIXES = ("/notifiche/conteggio", "/offline/stato", "/offline/pacchetto", "/sw.js", "/manifest.webmanifest")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = int(time.time())
            last = request.session.get("fasas_last_activity")
            timeout = request.fasas_config.session_timeout_minutes * 60
            if last and now - last > timeout:
                request.fasas_session_timeout = True
                logout(request)
                messages.warning(request, "Sessione scaduta per inattività: accedi di nuovo.")
                return redirect(f"{reverse(settings.LOGIN_URL)}?next={request.path}")
            # Le richieste automatiche (contatore notifiche, stato offline, service worker) non tengono viva la sessione.
            if not request.path.startswith(self.PASSIVE_PREFIXES):
                request.session["fasas_last_activity"] = now
        return self.get_response(request)


class LoginRequiredMiddleware:
    """Ogni pagina richiede l'accesso, tranne login, statici e API (che autenticano da sé)."""

    EXEMPT_PREFIXES = ("/accesso/", "/static/", "/api/", "/salute/")
    # Involucro dell'app (nessun dato) e servizi offline che rispondono da sé 401 senza sessione.
    EXEMPT_PATHS = {"/sw.js", "/manifest.webmanifest", "/offline/", "/offline/stato/", "/offline/pacchetto/",
                    "/offline/sincronizza/",
                    # caratteristiche pubbliche della firma con CIE (DPCM 22/02/2013, art. 57): nessun dato
                    "/firma/caratteristiche-firma-cie/"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (not request.user.is_authenticated and not request.path.startswith(self.EXEMPT_PREFIXES)
                and request.path not in self.EXEMPT_PATHS):
            return redirect(f"{reverse(settings.LOGIN_URL)}?next={request.path}")
        return self.get_response(request)
