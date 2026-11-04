import ipaddress
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from .models import Community, SystemConfig, config_scope


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
        with config_scope():  # configurazione letta al più una volta per richiesta
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


class RemoteAccessMiddleware:
    """
    Utente abilitato solo dalla struttura: se una sessione aperta in reparto arriva poi da fuori (es. il telefono
    passa dal Wi-Fi ai dati mobili) si chiude subito.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from fasas.accounts import twofactor

        user = request.user
        if user.is_authenticated and not twofactor.remote_allowed(user, request):
            logout(request)
            messages.error(request, twofactor.OUTSIDE_REFUSED)
            return redirect(settings.LOGIN_URL)
        return self.get_response(request)


class LoginRequiredMiddleware:
    """Ogni pagina richiede l'accesso, tranne login, statici e API (che autenticano da sé)."""

    EXEMPT_PREFIXES = ("/accesso/", "/static/", "/api/", "/salute/")
    # Involucro dell'app (nessun dato) e servizi offline che rispondono da sé 401 senza sessione.
    EXEMPT_PATHS = {"/sw.js", "/manifest.webmanifest", "/favicon.ico", "/firma/app/fasas-signer.apk", "/offline/",
                    "/offline/stato/",
                    "/offline/pacchetto/", "/offline/sincronizza/",
                    # caratteristiche pubbliche della firma con CIE (DPCM 22/02/2013, art. 57): nessun dato
                    "/firma/caratteristiche-firma-cie/"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (not request.user.is_authenticated and not request.path.startswith(self.EXEMPT_PREFIXES)
                and request.path not in self.EXEMPT_PATHS):
            return redirect(f"{reverse(settings.LOGIN_URL)}?next={request.path}")
        return self.get_response(request)


class ModuleSwitchMiddleware:
    """Le pagine di un modulo spento (Configurazione › Moduli) rispondono «funzione spenta»."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from django.shortcuts import render

        from . import modules

        match = request.resolver_match
        module = modules.for_view(match.namespace, match.url_name) if match else None
        if module is None or modules.is_on(module.key, getattr(request, "fasas_config", None)):
            return None
        return render(request, "core/module_off.html", {"module": module}, status=404)


class ApiSwitchMiddleware:
    """API REST /api/v1/ spenta di default (FASAS_API_ENABLED): risponde 404 come se non esistesse."""

    PREFIX = "/api/v1/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.PREFIX) and not settings.FASAS_API_ENABLED:
            from django.http import HttpResponseNotFound

            return HttpResponseNotFound("API non attiva su questo server.", content_type="text/plain; charset=utf-8")
        return self.get_response(request)
