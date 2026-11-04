"""
API del FASAS Signer (/api/firma/v1/).

Autenticazione solo con «Authorization: Bearer <token del dispositivo>»: i cookie di sessione vengono ignorati,
quindi una pagina web non può usare queste API a nome dell'utente (per questo l'esenzione CSRF è sicura).
Il server non abilita CORS. Ogni risposta riuscita di un passo contiene il nonce del passo successivo.
"""
import json
import time

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from fasas.audit.context import audit_context
from fasas.core.middleware import client_ip

from . import cie, external
from .models import SignatureRequest
from .providers import SignatureError

MAX_BODY = 64 * 1024
MAX_WAIT = 10
PAIRING_LIMIT = 10  # abbinamenti falliti per IP ogni 10 minuti


def _json(data, status=200):
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _error(exc, status=400):
    return _json({"error": exc.code, "message": str(exc)}, status=status)


def _body(request):
    if len(request.body) > MAX_BODY:
        raise SignatureError("Richiesta troppo grande.", "too_large")
    try:
        data = json.loads(request.body or b"{}")
    except ValueError as exc:
        raise SignatureError("JSON non valido.", "bad_request") from exc
    if not isinstance(data, dict):
        raise SignatureError("JSON non valido.", "bad_request")
    return data


def _https_required(request):
    return not request.is_secure() and not settings.FASAS_CIE_ALLOW_HTTP


def device_api(view):
    """Autentica il dispositivo, imposta il contesto dell'audit e gestisce gli errori in modo uniforme."""

    @csrf_exempt
    @never_cache
    @transaction.non_atomic_requests
    def wrapper(request, *args, **kwargs):
        if _https_required(request):
            return _json({"error": "https_required", "message": "Connessione HTTPS obbligatoria."}, status=403)
        if not cie.is_enabled():
            return _json({"error": "disabled", "message": "Firma con CIE disattivata sul server."}, status=503)
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        device = cie.authenticate_device(token)
        if device is None:
            with audit_context(ip=client_ip(request), source="fasas-signer"):
                if token:
                    cie.deny("Token del dispositivo di firma non valido o revocato.", code="bad_token")
            return _json({"error": "unauthorized", "message": "Dispositivo non abbinato o revocato."}, status=401)
        request_id = kwargs.get("request_id")
        with audit_context(user=device.user, ip=client_ip(request), source="fasas-signer"):
            try:
                return view(request, device, *args, **kwargs)
            except SignatureError as exc:
                if request_id:
                    cie.handle_failure(request_id, exc)
                if exc.code in cie.SECURITY_CODES:
                    target = SignatureRequest.objects.filter(pk=request_id, user=device.user).first() if request_id else None
                    cie.deny(f"FASAS Signer «{device.name}»: {exc}", user=device.user, obj=target,
                             request_id=str(request_id or ""), code=exc.code)
                status = {"not_found": 404, "wrong_device": 409, "bad_state": 409, "bad_nonce": 409, "expired": 410,
                          "forbidden": 403}.get(exc.code, 400)
                return _error(exc, status)

    return wrapper


@csrf_exempt
@never_cache
@require_POST
def pair(request):
    """Abbinamento: codice monouso generato nel FASAS → token del dispositivo (restituito una sola volta)."""
    if _https_required(request):
        return _json({"error": "https_required", "message": "Connessione HTTPS obbligatoria."}, status=403)
    ip = client_ip(request)
    key = f"fasas-cie-pairing:{ip}"
    attempts = cache.get(key, 0)
    if attempts >= PAIRING_LIMIT:
        return _json({"error": "rate_limited", "message": "Troppi tentativi: riprovare tra qualche minuto."}, status=429)
    try:
        data = _body(request)
        device, token = cie.pair_device(data.get("code", ""), str(data.get("name", ""))[:100],
                                        str(data.get("platform", "")), str(data.get("app_version", "")))
    except SignatureError as exc:
        cache.set(key, attempts + 1, 600)  # contano solo i tentativi falliti (codici indovinati a caso)
        with audit_context(ip=ip, source="fasas-signer"):
            cie.deny("Abbinamento del FASAS Signer con codice non valido o scaduto.", code=exc.code)
        return _error(exc, 400)
    return _json({"token": token, "device": device.pk, "user": str(device.user),
                  "fiscal_code_configured": bool(device.user.fiscal_code)}, status=201)


@require_GET
@device_api
def me(request, device):
    return _json({"device": device.pk, "name": device.name, "user": str(device.user),
                  "fiscal_code_configured": bool(device.user.fiscal_code),
                  "trust_configured": bool(external.trust_roots())})


@require_POST
@device_api
def device_status(request, device):
    return _json({"status": cie.update_device_status(device, _body(request))})


@require_GET
@device_api
def pending(request, device):
    """Richieste in attesa per l'utente del dispositivo (attesa breve opzionale: ?attesa=secondi, max 10)."""
    try:
        wait = max(0, min(MAX_WAIT, int(request.GET.get("attesa", "0"))))
    except ValueError:
        wait = 0
    deadline = time.monotonic() + wait
    while True:
        items = [cie.describe(r) for r in cie.pending_for(device)[:5]]
        if items or time.monotonic() >= deadline:
            return _json({"requests": items})
        time.sleep(1)


@require_POST
@device_api
def claim(request, device, request_id):
    signature_request, nonce = cie.claim(request_id, device)
    return _json({**cie.describe(signature_request), "nonce": nonce})


@require_POST
@device_api
def state(request, device, request_id):
    data = _body(request)
    signature_request, nonce = cie.report_state(request_id, device, data.get("nonce"), data.get("state"),
                                                data.get("attempts_left"))
    return _json({"status": signature_request.status, "nonce": nonce})


@require_POST
@device_api
def certificate(request, device, request_id):
    data = _body(request)
    signature_request, nonce, prepared = cie.submit_certificate(request_id, device, data.get("nonce"),
                                                                data.get("certificate", ""))
    return _json({
        "status": signature_request.status, "nonce": nonce, "mechanism": "SHA256-RSA-PKCS",
        # Il dispositivo firma «to_be_signed» con CKM_SHA256_RSA_PKCS oppure «digest_info» con CKM_RSA_PKCS:
        # il risultato è lo stesso (RSA PKCS#1 v1.5 con SHA-256 sugli attributi firmati CMS)
        "to_be_signed": prepared.signed_attrs, "digest": external.b64(prepared.digest),
        "digest_info": external.b64(prepared.digest_info), "verify_code": signature_request.verify_code,
    })


@require_POST
@device_api
def sign(request, device, request_id):
    data = _body(request)
    signature_request = cie.submit_signature(request_id, device, data.get("nonce"), data.get("signature", ""))
    return _json({"status": signature_request.status,
                  "version": signature_request.signature.signed_version.number if signature_request.signature else None,
                  "verification": {k: signature_request.verification.get(k) for k in
                                   ("intact", "valid", "trusted", "level", "timestamped")}})


@require_POST
@device_api
def error(request, device, request_id):
    data = _body(request)
    signature_request = cie.report_error(request_id, device, data.get("nonce"), str(data.get("code", "")))
    return _json({"status": signature_request.status, "error": signature_request.error_code})
