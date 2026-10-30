import datetime
import functools

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST
from django.views.defaults import page_not_found

from fasas.core.encryption import DecryptionError, decrypt, encrypt, read_encrypted
from fasas.documents.models import DocumentVersion
from fasas.documents.services import read_version

from . import cie, external
from .forms import CIESignForm, CredentialForm, RemoteCredentialForm, SendOTPForm, SignForm
from .models import SignatureRequest, SignerDevice, SigningCredential
from .providers import SignatureError, signature_level, verify_pdf
from .services import register_pkcs12, register_remote, request_otp, sign_version

TOKEN_KEY = "fasas_csc_token"
TOKEN_MINUTES = 5


PAIRING_KEY = "fasas_cie_pairing"


def can_configure_signature(user):
    return user.has_perm("signatures.sign_document") or user.has_perm("signatures.sign_with_cie")


def credential_view(request):
    """Impostazioni «Firma digitale»: le quattro modalità, ben distinte per valore giuridico."""
    user = request.user
    if not can_configure_signature(user):
        raise PermissionDenied
    can_certificate = user.has_perm("signatures.sign_document")
    can_cie = user.has_perm("signatures.sign_with_cie")
    credential = SigningCredential.objects.filter(user=user).first()
    form = CredentialForm(request.POST or None, request.FILES or None, prefix="p12")
    remote_form = RemoteCredentialForm(request.POST or None, prefix="remote",
                                       initial={"remote_user_id": getattr(credential, "remote_user_id", "")})
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "cie-pair" and can_cie:
            try:
                code = cie.create_pairing(user)
            except SignatureError as exc:
                messages.error(request, str(exc))
            else:
                request.session[PAIRING_KEY] = {"code": code, "expires": (timezone.now() + datetime.timedelta(
                    minutes=settings.FASAS_CIE_PAIRING_MINUTES)).isoformat()}
            return redirect(f"{reverse('signatures:credential')}#cie")
        if action == "cie-revoke" and can_cie:
            device = get_object_or_404(SignerDevice, pk=request.POST.get("device"), user=user, revoked_at__isnull=True)
            cie.revoke_device(device, user)
            messages.success(request, f"Dispositivo «{device.name}» revocato: non può più firmare.")
            return redirect(f"{reverse('signatures:credential')}#cie")
        if not can_certificate:
            raise PermissionDenied
        if "p12-certificate" in request.FILES and form.is_valid():
            try:
                register_pkcs12(user, form.cleaned_data["certificate"].read(), form.cleaned_data["passphrase"])
            except SignatureError as exc:
                form.add_error("passphrase", str(exc))
            else:
                messages.success(request, "Certificato di firma registrato e cifrato.")
                return redirect("signatures:credential")
        elif "remote-remote_user_id" in request.POST and remote_form.is_valid():
            data = remote_form.cleaned_data
            try:
                register_remote(user, data["remote_user_id"], data["password"], data["credential_id"])
            except SignatureError as exc:
                remote_form.add_error(None, str(exc))
            else:
                messages.success(request, "Firma remota collegata: certificato letto dal prestatore.")
                return redirect("signatures:credential")
    try:
        level, level_error = signature_level(), ""
    except SignatureError as exc:
        level, level_error = "", str(exc)
    pairing = request.session.pop(PAIRING_KEY, None)
    if pairing and timezone.now() > datetime.datetime.fromisoformat(pairing["expires"]):
        pairing = None
    devices = _devices(user) if can_cie else []
    return render(request, "signatures/credential.html", {
        "credential": credential, "form": form, "remote_form": remote_form, "can_certificate": can_certificate,
        "can_cie": can_cie, "remote_configured": bool(settings.FASAS_CSC_SERVICE_URL),
        "provider_name": settings.FASAS_CSC_PROVIDER_NAME, "level": level, "level_error": level_error,
        "tsa": bool(settings.FASAS_SIGNATURE_TSA_URL), "cie": cie_readiness(user, devices) if can_cie else None,
        "devices": devices, "pairing": pairing, "server_url": request.build_absolute_uri("/"),
        "pairing_minutes": settings.FASAS_CIE_PAIRING_MINUTES,
        "tests": SignatureRequest.objects.filter(user=user, purpose=SignatureRequest.Purpose.TEST)[:5] if can_cie else [],
    })


def cie_readiness(user, devices):
    """Elenco dei requisiti per firmare con la CIE, ciascuno con esito e istruzioni."""
    online = [d for d in devices if d.is_online]
    latest = max(devices, key=lambda d: d.status_at or d.created_at) if devices else None
    status = latest.status if latest else {}
    checks = [
        ("Firma con CIE attiva sul server", cie.is_enabled(), "Impostare FASAS_CIE_ENABLED=1."),
        ("CA della CIE configurate (verifica della catena)", bool(external.trust_roots()),
         "L'amministratore deve indicare in FASAS_CIE_TRUST_ROOTS il file PEM con le CA della CIE."),
        ("Codice fiscale nel tuo profilo", bool(user.fiscal_code),
         "Serve per controllare che la carta sia la tua: chiedilo all'amministratore."),
        ("FASAS Signer abbinato", bool(devices), "Installa FASAS Signer sul computer con il lettore e abbinalo qui sotto."),
        ("FASAS Signer in linea", bool(online), "Avvia FASAS Signer sul computer con il lettore."),
        ("Software CIE (middleware) trovato", bool(status.get("middleware_found")),
         "Installa il Software CIE del Ministero dell'Interno sul computer del Signer."),
        ("Lettore collegato", bool(status.get("readers")), "Collega un lettore NFC/contactless compatibile con la CIE."),
    ]
    return {"checks": [{"label": label, "ok": ok, "help": help_text} for label, ok, help_text in checks],
            "ready": all(ok for _, ok, _ in checks[:5]), "status": status, "latest": latest,
            "revocation": settings.FASAS_CIE_REVOCATION,
            "timestamp": settings.FASAS_CIE_TIMESTAMP and bool(settings.FASAS_SIGNATURE_TSA_URL)}


@permission_required("signatures.manage_signer_devices", raise_exception=True)
def devices_admin(request):
    """Amministratore: elenco e revoca dei dispositivi di firma di tutti gli utenti (es. computer smarrito)."""
    if request.method == "POST":
        device = get_object_or_404(SignerDevice, pk=request.POST.get("device"), revoked_at__isnull=True)
        cie.revoke_device(device, request.user)
        messages.success(request, f"Dispositivo «{device.name}» di {device.user} revocato.")
        return redirect("signatures:devices")
    return render(request, "signatures/devices.html", {
        "devices": SignerDevice.objects.select_related("user").order_by("revoked_at", "-last_seen_at")[:200],
    })


def _session_token(request, credential):
    """Token del prestatore conservato (cifrato, pochi minuti) tra l'invio dell'SMS e la firma."""
    stored = request.session.get(TOKEN_KEY)
    if not stored or stored.get("credential") != credential.remote_credential_id:
        return None
    if timezone.now() > datetime.datetime.fromisoformat(stored["expires"]):
        request.session.pop(TOKEN_KEY, None)
        return None
    try:
        return decrypt(stored["value"].encode()).decode()
    except DecryptionError:
        return None


@permission_required("signatures.sign_document", raise_exception=True)
def sign_version_view(request, pk):
    version = get_object_or_404(DocumentVersion.objects.select_related("document__guest"), pk=pk)
    credential = SigningCredential.objects.filter(user=request.user).first()
    remote = credential is not None and credential.kind == SigningCredential.Kind.REMOTE
    token = _session_token(request, credential) if remote else None

    if request.method == "POST" and request.POST.get("action") == "send_otp" and remote:
        otp_form = SendOTPForm(request.POST)
        otp_form.is_valid()
        try:
            token = request_otp(request.user, otp_form.cleaned_data.get("password", ""))
        except SignatureError as exc:
            messages.error(request, str(exc))
        else:
            request.session[TOKEN_KEY] = {
                "value": encrypt(token.encode()).decode(), "credential": credential.remote_credential_id,
                "expires": (timezone.now() + datetime.timedelta(minutes=TOKEN_MINUTES)).isoformat(),
            }
            messages.success(request, "OTP inviato via SMS al numero registrato presso il prestatore.")
        return redirect("documents:sign", pk=pk)

    form = SignForm(request.POST or None, credential=credential, has_token=bool(token))
    if request.method == "POST" and form.is_valid():
        secrets = {**form.secrets(), "token": token}
        try:
            signature = sign_version(version, request.user, secrets, form.cleaned_data["reason"])
        except SignatureError as exc:
            form.add_error(None, str(exc))
        else:
            request.session.pop(TOKEN_KEY, None)
            messages.success(request, f"Documento firmato ({signature.signature_format}): "
                                      f"creata la versione {signature.signed_version.number}.")
            return redirect(version.document.get_absolute_url())
    return render(request, "signatures/sign.html", {
        "form": form, "version": version, "guest": version.document.guest, "credential": credential,
        "remote": remote, "token_active": bool(token), "needs_password": settings.FASAS_CSC_AUTH == "basic",
        "provider_name": settings.FASAS_CSC_PROVIDER_NAME,
    })


@permission_required("documents.view_document", raise_exception=True)
def verify_version_view(request, pk):
    version = get_object_or_404(DocumentVersion.objects.select_related("document__guest"), pk=pk)
    results = verify_pdf(read_version(version, user=request.user)) if version.is_pdf else []
    return render(request, "signatures/verify.html", {
        "version": version, "document": version.document, "guest": version.document.guest, "results": results,
        "trust_configured": bool(settings.FASAS_SIGNATURE_TRUST_ROOTS),
    })


# --- Firma con CIE (FASAS Sign) ----------------------------------------------------------------------------

STEPS = [
    ("waiting", "In attesa della CIE"), ("card", "Carta rilevata"), ("authorizing", "Autorizzazione richiesta"),
    ("signing", "Firma in corso"), ("verifying", "Verifica della firma"), ("signed", "Documento firmato correttamente"),
]


def own_request(view):
    """
    Solo il firmatario vede la propria richiesta; per gli altri non esiste. Si risponde 404 senza sollevare
    eccezioni, così la transazione non viene annullata e il tentativo resta nell'audit.
    """
    @functools.wraps(view)
    def wrapper(request, request_id):
        signature_request = (SignatureRequest.objects.select_related("version__document__guest", "device", "signature")
                             .filter(pk=request_id).first())
        if signature_request is None or signature_request.user_id != request.user.pk:
            cie.deny("Accesso a una richiesta di firma CIE di un altro utente o inesistente.", user=request.user,
                     obj=signature_request, request_id=str(request_id), code="not_found")
            return page_not_found(request, Http404())
        return view(request, cie.expire_if_needed(signature_request))

    return wrapper


def _devices(user):
    return list(SignerDevice.objects.filter(user=user, revoked_at__isnull=True))


@permission_required("signatures.sign_with_cie", raise_exception=True)
def cie_sign_view(request, pk):
    """Anteprima completa del PDF e avvio della firma: la versione si blocca solo quando si conferma."""
    version = get_object_or_404(DocumentVersion.objects.select_related("document__guest"), pk=pk)
    if not request.user.has_perm("documents.view_document"):
        raise PermissionDenied
    active = SignatureRequest.objects.filter(version=version, user=request.user,
                                             status__in=SignatureRequest.ACTIVE).first()
    if active is not None and cie.expire_if_needed(active).is_active:
        return redirect("signatures:cie_request", request_id=active.pk)
    form = CIESignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            signature_request = cie.create_request(version, request.user, form.cleaned_data["reason"])
        except SignatureError as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("signatures:cie_request", request_id=signature_request.pk)
    document = version.document
    return render(request, "signatures/cie_sign.html", {
        "form": form, "version": version, "document": document, "guest": document.guest,
        "is_current": document.current_version.pk == version.pk, "devices": _devices(request.user),
        "trust_configured": bool(external.trust_roots()), "fiscal_code": request.user.fiscal_code,
        "preview_url": reverse("documents:view", args=[version.pk]), "enabled": cie.is_enabled(),
    })


@permission_required("signatures.sign_with_cie", raise_exception=True)
@own_request
def cie_request_view(request, signature_request):
    test = signature_request.purpose == SignatureRequest.Purpose.TEST
    preview_url = (reverse("signatures:cie_test_file", args=[signature_request.pk]) if test
                   else reverse("documents:view", args=[signature_request.version_id]))
    return render(request, "signatures/cie_request.html", {
        "req": signature_request, "steps": STEPS, "test": test, "preview_url": preview_url,
        "guest": None if test else signature_request.version.document.guest,
        "document": None if test else signature_request.version.document,
        "status_url": reverse("signatures:cie_status", args=[signature_request.pk]),
        "devices": _devices(request.user),
    })


def status_payload(signature_request):
    order = [code for code, _ in STEPS]
    devices = SignerDevice.objects.filter(user=signature_request.user, revoked_at__isnull=True)
    online = any(d.is_online for d in devices)
    payload = {
        "status": signature_request.status, "label": signature_request.get_status_display(),
        "document_state": signature_request.document_state, "active": signature_request.is_active,
        "step": order.index(signature_request.status) if signature_request.status in order else None,
        "verify_code": signature_request.verify_code, "error": signature_request.error_message,
        "error_code": signature_request.error_code, "pin_attempts_left": signature_request.pin_attempts_left,
        "expires_in": max(0, int((signature_request.expires_at - timezone.now()).total_seconds())),
        "device": signature_request.device.name if signature_request.device else None,
        "devices": devices.count(), "device_online": online, "result_url": None,
        "test_card": signature_request.is_test_card,
    }
    if signature_request.status == SignatureRequest.Status.SIGNED:
        if signature_request.signature_id:
            payload["result_url"] = signature_request.version.document.get_absolute_url()
            payload["version"] = signature_request.signature.signed_version.number
        else:
            payload["result_url"] = reverse("signatures:cie_test_file", args=[signature_request.pk]) + "?firmato=1"
        payload["verification"] = {k: signature_request.verification.get(k) for k in
                                   ("intact", "valid", "trusted", "level", "timestamped", "note", "chain_note")}
    return payload


@never_cache
@permission_required("signatures.sign_with_cie", raise_exception=True)
@own_request
def cie_status(request, signature_request):
    return JsonResponse(status_payload(signature_request))


@require_POST
@permission_required("signatures.sign_with_cie", raise_exception=True)
@own_request
def cie_cancel(request, signature_request):
    try:
        cie.cancel_request(signature_request, request.user)
    except SignatureError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, "Firma annullata: il documento è di nuovo modificabile.")
    if signature_request.purpose == SignatureRequest.Purpose.TEST:
        return redirect("signatures:credential")
    return redirect(signature_request.version.document.get_absolute_url())


@require_POST
@permission_required("signatures.sign_with_cie", raise_exception=True)
@own_request
def cie_retry(request, signature_request):
    try:
        new = cie.retry_request(signature_request, request.user)
    except SignatureError as exc:
        messages.error(request, str(exc))
        return redirect("signatures:cie_request", request_id=signature_request.pk)
    return redirect("signatures:cie_request", request_id=new.pk)


@require_POST
@permission_required("signatures.sign_with_cie", raise_exception=True)
def cie_test(request):
    try:
        signature_request = cie.create_test_request(request.user)
    except SignatureError as exc:
        messages.error(request, str(exc))
        return redirect("signatures:credential")
    return redirect("signatures:cie_request", request_id=signature_request.pk)


@xframe_options_sameorigin
@permission_required("signatures.sign_with_cie", raise_exception=True)
@own_request
def cie_test_file(request, signature_request):
    """PDF della prova (nessun dato sanitario): l'originale per l'anteprima o, a firma riuscita, quello firmato."""
    if signature_request.purpose != SignatureRequest.Purpose.TEST:
        raise Http404
    signed = signature_request.status == SignatureRequest.Status.SIGNED
    if not signature_request.result_storage or (request.GET.get("firmato") and not signed):
        raise Http404
    data = read_encrypted(signature_request.result_storage)
    inline = not request.GET.get("firmato")
    name = "prova_firma_CIE_firmata.pdf" if signed else "prova_firma_CIE.pdf"
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(not inline, name)
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
