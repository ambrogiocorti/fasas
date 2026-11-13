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
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST
from django.views.defaults import page_not_found

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import DecryptionError, decrypt, encrypt, read_encrypted
from fasas.documents.cie_gate import cie_gate
from fasas.documents.models import Document, DocumentVersion
from fasas.documents.services import read_version
from fasas.guests.models import Guest

from . import cie, external, fea_terms
from .forms import CIESignForm, CredentialForm, FasasPinForm, RemoteCredentialForm, SendOTPForm, SignForm
from .models import FEAAcceptance, SignatureRequest, SignerDevice, SigningCredential
from .providers import SignatureError, signature_level, verify_pdf
from .services import bulk_limit, register_pkcs12, register_remote, request_otp, sign_version, sign_versions

TOKEN_KEY = "fasas_csc_token"
TOKEN_MINUTES = 5


PAIRING_KEY = "fasas_cie_pairing"


def can_configure_signature(user):
    return (user.has_perm("signatures.sign_document") or user.has_perm("signatures.sign_with_cie")
            or cie.can_use_device(user))


def credential_view(request):
    """Impostazioni «Firma digitale»: le quattro modalità, ben distinte per valore giuridico."""
    user = request.user
    if not can_configure_signature(user):
        raise PermissionDenied
    can_certificate = user.has_perm("signatures.sign_document")
    can_cie = cie.can_use_device(user)  # firma con CIE o verifica per aprire i documenti; spenta: niente abbinamenti
    can_cie_sign = user.has_perm("signatures.sign_with_cie") and cie.is_enabled()
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
        if action == "cie-enroll" and can_cie:
            try:
                enroll_request = cie.create_enroll_request(user)
            except SignatureError as exc:
                messages.error(request, str(exc))
            else:
                return redirect("signatures:cie_request", request_id=enroll_request.pk)
            return redirect(f"{reverse('signatures:credential')}#cie-senza-pin")
        if action == "fasas-pin" and can_cie:
            enrollment = cie.enrollment_of(user)
            pin_form = FasasPinForm(request.POST, enrollment=enrollment)
            if enrollment is not None and pin_form.is_valid():
                cie.set_fasas_pin(enrollment, pin_form.cleaned_data["pin"], user)
                messages.success(request, "PIN FASAS salvato.")
                return redirect(f"{reverse('signatures:credential')}#cie-senza-pin")
            for error in pin_form.errors.values():
                messages.error(request, " ".join(error))
            return redirect(f"{reverse('signatures:credential')}#cie-senza-pin")
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
        elif "remote-remote_user_id" in request.POST and remote_on() and remote_form.is_valid():
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
        "can_cie": can_cie, "can_cie_sign": can_cie_sign, "remote_configured": remote_on(),
        "documents_cie_required": cie.documents_gate_on() and cie.is_enabled(),
        "documents_cie_minutes": request.fasas_config.documents_cie_minutes, "fiscal_code": user.fiscal_code,
        "provider_name": settings.FASAS_CSC_PROVIDER_NAME, "level": level, "level_error": level_error,
        "tsa": bool(settings.FASAS_SIGNATURE_TSA_URL), "cie": cie_readiness(user, devices) if can_cie else None,
        "devices": devices, "pairing": pairing, "server_url": request.build_absolute_uri("/"),
        "pairing_minutes": settings.FASAS_CIE_PAIRING_MINUTES,
        "tests": SignatureRequest.objects.filter(user=user, purpose=SignatureRequest.Purpose.TEST)[:5] if can_cie_sign else [],
        "acceptance": cie.valid_acceptance(user) if can_cie_sign else None,
        "acceptance_required": settings.FASAS_FEA_REQUIRE_ACCEPTANCE, "terms_draft": fea_terms.is_draft(),
        "nis_enabled": can_cie and request.fasas_config.documents_verification == "nis",
        "enrollment": cie.enrollment_of(user) if can_cie else None, "pin_form": FasasPinForm(enrollment=None),
        "card_pin_tested": cie.card_pin_tested() if can_cie_sign else True,
    })


def remote_on():
    """Firma remota qualificata: prestatore configurato sul server e modulo acceso."""
    from fasas.core.modules import is_on

    return bool(settings.FASAS_CSC_SERVICE_URL) and is_on("remote_signature")


def cie_readiness(user, devices):
    """Elenco dei requisiti per firmare con la CIE, ciascuno con esito e istruzioni."""
    online = [d for d in devices if d.is_online]
    latest = max(devices, key=lambda d: d.status_at or d.created_at) if devices else None
    status = latest.status if latest else {}
    checks = [
        ("Firma con CIE attiva sul server", cie.is_enabled(), "Impostare FASAS_CIE_ENABLED=1."),
        ("CA della CIE configurate (verifica della catena)", bool(external.trust_roots()),
         "Il gestore del sistema deve indicare in FASAS_CIE_TRUST_ROOTS il file PEM con le CA della CIE."),
        ("Codice fiscale nel tuo profilo", bool(user.fiscal_code),
         "Serve per controllare che la carta sia la tua: chiedilo al gestore del sistema."),
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
    """Gestore del sistema: elenco e revoca dei dispositivi di firma di tutti gli utenti (es. computer smarrito)."""
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
    if (gate := cie_gate(request, version.document.guest, version.document)) is not None:
        return gate
    credential = SigningCredential.objects.filter(user=request.user).first()
    remote = credential is not None and credential.kind == SigningCredential.Kind.REMOTE
    if remote and not remote_on():
        messages.error(request, "La firma remota qualificata è spenta in questa struttura (Configurazione › Moduli).")
        return redirect(version.document.get_absolute_url())
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


@permission_required("signatures.sign_document", raise_exception=True)
def sign_many_view(request):
    """Firma di più documenti in una volta: una passphrase, oppure un solo PIN e OTP se il prestatore lo consente."""
    from urllib.parse import urlencode

    from fasas.documents.views import documents_to_sign

    pending = {p["version"].pk: p for p in documents_to_sign()}
    wanted = []
    for raw in request.POST.getlist("v") or request.GET.getlist("v"):
        if raw.isdigit() and int(raw) in pending and int(raw) not in wanted:
            wanted.append(int(raw))
    if not wanted:
        messages.error(request, "Selezionare almeno un documento da firmare.")
        return redirect("documents:to_sign")
    selected = [pending[pk] for pk in wanted]
    here = f"{reverse('documents:sign_many')}?{urlencode([('v', pk) for pk in wanted])}"
    for item in selected:
        if (gate := cie_gate(request, item["document"].guest, item["document"], next_url=here)) is not None:
            return gate
    credential = SigningCredential.objects.filter(user=request.user).first()
    if credential is None:
        messages.error(request, "Prima di firmare configura il tuo strumento di firma.")
        return redirect("signatures:credential")
    remote = credential.kind == SigningCredential.Kind.REMOTE
    if remote and not remote_on():
        messages.error(request, "La firma remota qualificata è spenta in questa struttura (Configurazione › Moduli).")
        return redirect("documents:to_sign")
    limit = bulk_limit(credential)
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
            messages.success(request, "OTP inviato via SMS: vale per tutti i documenti selezionati.")
        return redirect(here)

    form = SignForm(request.POST or None, credential=credential, has_token=bool(token))
    form.fields["confirm"].label = f"Ho letto i {len(selected)} documenti elencati e intendo firmarli"
    if len(selected) == 1:
        form.fields["confirm"].label = "Ho letto il documento e intendo firmarlo"
    if request.method == "POST" and form.is_valid():
        if len(selected) > limit:
            form.add_error(None, f"Si possono firmare al massimo {limit} documenti per volta.")
        else:
            try:
                signatures = sign_versions([p["version"] for p in selected], request.user,
                                           {**form.secrets(), "token": token}, form.cleaned_data["reason"])
            except SignatureError as exc:
                form.add_error(None, str(exc))
            else:
                request.session.pop(TOKEN_KEY, None)
                messages.success(request, f"Firmati {len(signatures)} documenti "
                                          f"({signatures[0].signature_format}): creata una nuova versione per ciascuno.")
                return redirect("documents:to_sign")
    return render(request, "signatures/sign_many.html", {
        "form": form, "selected": selected, "credential": credential, "remote": remote, "limit": limit,
        "too_many": len(selected) > limit, "token_active": bool(token),
        "needs_password": settings.FASAS_CSC_AUTH == "basic", "provider_name": settings.FASAS_CSC_PROVIDER_NAME,
    })


@permission_required("documents.view_document", raise_exception=True)
def verify_version_view(request, pk):
    version = get_object_or_404(DocumentVersion.objects.select_related("document__guest"), pk=pk)
    if (gate := cie_gate(request, version.document.guest, version.document)) is not None:
        return gate
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


ACCESS_STEPS = [
    ("waiting", "In attesa della CIE"), ("card", "Carta rilevata"), ("authorizing", "PIN sul telefono"),
    ("signing", "La carta conferma l'identità"), ("verifying", "Verifica del certificato"),
    ("signed", "Identità verificata"),
]
NIS_STEPS = [
    ("waiting", "In attesa del telefono"), ("authorizing", "CIE appoggiata e PIN FASAS sul telefono"),
    ("verifying", "Verifica della carta"), ("signed", "Identità verificata"),
]
ENROLL_STEPS = [
    ("waiting", "In attesa del telefono"), ("authorizing", "Appoggia la CIE al telefono"),
    ("verifying", "Verifica della carta"), ("signed", "CIE registrata"),
]
ACCESS_NEXT = "fasas_cie_access_next"
NO_SIGN_PURPOSES = (SignatureRequest.Purpose.ACCESS, SignatureRequest.Purpose.ENROLL)


def _steps(signature_request):
    if signature_request.purpose == SignatureRequest.Purpose.ENROLL:
        return ENROLL_STEPS
    if signature_request.purpose == SignatureRequest.Purpose.ACCESS:
        return NIS_STEPS if signature_request.access_method == "nis" else ACCESS_STEPS
    return STEPS


def cie_user_required(view):
    """Firma con CIE oppure verifica di identità per i documenti (chi può usare un FASAS Signer)."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.has_perm(cie.PERMISSION) or cie.can_use_device(request.user)):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _access_next(request, signature_request):
    """Dove tornare dopo la verifica: la pagina del documento chiesta all'inizio (solo indirizzi di questo sito)."""
    saved = request.session.get(ACCESS_NEXT, {}).get(str(signature_request.pk))
    if saved:
        return saved
    if signature_request.access_document_id:
        return signature_request.access_document.get_absolute_url()
    return reverse("documents:guest_list", args=[signature_request.access_guest_id])


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
        if not (signature_request.purpose in NO_SIGN_PURPOSES or request.user.has_perm(cie.PERMISSION)):
            raise PermissionDenied
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
    if (gate := cie_gate(request, version.document.guest, version.document)) is not None:
        return gate
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


@cie_user_required
@own_request
def cie_request_view(request, signature_request):
    if signature_request.purpose in NO_SIGN_PURPOSES:
        return render(request, "signatures/cie_request.html", {
            "req": signature_request, "steps": _steps(signature_request), "access": True, "test": False,
            "by_nis": signature_request.access_method == "nis",
            "enroll": signature_request.purpose == SignatureRequest.Purpose.ENROLL,
            "guest": signature_request.access_guest, "document": signature_request.access_document,
            "status_url": reverse("signatures:cie_status", args=[signature_request.pk]),
            "devices": _devices(request.user), "minutes": request.fasas_config.documents_cie_minutes,
        })
    test = signature_request.purpose != SignatureRequest.Purpose.DOCUMENT  # prova o accettazione: nessun ospite
    preview_url = (reverse("signatures:cie_test_file", args=[signature_request.pk]) if test
                   else reverse("documents:view", args=[signature_request.version_id]))
    return render(request, "signatures/cie_request.html", {
        "req": signature_request, "steps": STEPS, "test": test, "preview_url": preview_url,
        "acceptance": signature_request.purpose == SignatureRequest.Purpose.ACCEPTANCE,
        "guest": None if test else signature_request.version.document.guest,
        "document": None if test else signature_request.version.document,
        "status_url": reverse("signatures:cie_status", args=[signature_request.pk]),
        "devices": _devices(request.user),
    })


def status_payload(signature_request, result_url=None):
    steps = _steps(signature_request)
    order = [code for code, _ in steps]
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
    if signature_request.purpose in NO_SIGN_PURPOSES:
        payload["access"] = True
        payload["by_nis"] = signature_request.access_method == "nis"
        payload["enroll"] = signature_request.purpose == SignatureRequest.Purpose.ENROLL
        payload["label"] = {**dict(steps), "failed": "Verifica non riuscita"}.get(
            signature_request.status, payload["label"])
    if signature_request.status == SignatureRequest.Status.SIGNED:
        if signature_request.purpose == SignatureRequest.Purpose.ENROLL:
            payload["result_url"] = reverse("signatures:credential") + "#cie-senza-pin"
        elif signature_request.purpose == SignatureRequest.Purpose.ACCESS:
            payload["result_url"] = result_url
        elif signature_request.signature_id:
            payload["result_url"] = signature_request.version.document.get_absolute_url()
            payload["version"] = signature_request.signature.signed_version.number
        elif signature_request.purpose == SignatureRequest.Purpose.ACCEPTANCE:
            acceptance = getattr(signature_request, "fea_acceptance", None)
            payload["result_url"] = reverse("signatures:fea_file", args=[acceptance.pk]) if acceptance else None
        else:
            payload["result_url"] = reverse("signatures:cie_test_file", args=[signature_request.pk]) + "?firmato=1"
        payload["verification"] = {k: signature_request.verification.get(k) for k in
                                   ("intact", "valid", "trusted", "level", "timestamped", "note", "chain_note")}
    return payload


@never_cache
@cie_user_required
@own_request
def cie_status(request, signature_request):
    result_url = (_access_next(request, signature_request)
                  if signature_request.purpose == SignatureRequest.Purpose.ACCESS else None)
    return JsonResponse(status_payload(signature_request, result_url))


@require_POST
@cie_user_required
@own_request
def cie_cancel(request, signature_request):
    try:
        cie.cancel_request(signature_request, request.user)
    except SignatureError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, "Verifica annullata." if signature_request.purpose == SignatureRequest.Purpose.ACCESS
                      else "Firma annullata: il documento è di nuovo modificabile.")
    if signature_request.purpose == SignatureRequest.Purpose.ACCESS:
        return redirect("documents:guest_list", guest_pk=signature_request.access_guest_id)
    if signature_request.purpose != SignatureRequest.Purpose.DOCUMENT:
        return redirect("signatures:credential")
    return redirect(signature_request.version.document.get_absolute_url())


@require_POST
@cie_user_required
@own_request
def cie_retry(request, signature_request):
    try:
        new = cie.retry_request(signature_request, request.user)
    except SignatureError as exc:
        messages.error(request, str(exc))
        return redirect("signatures:cie_request", request_id=signature_request.pk)
    if signature_request.purpose == SignatureRequest.Purpose.ACCESS:
        saved = request.session.get(ACCESS_NEXT, {})
        if str(signature_request.pk) in saved:
            saved[str(new.pk)] = saved[str(signature_request.pk)]
            request.session[ACCESS_NEXT] = saved
    return redirect("signatures:cie_request", request_id=new.pk)


@permission_required("documents.view_document", raise_exception=True)
def cie_access(request):
    """
    Verifica di identità con la CIE prima di aprire, scaricare o modificare un documento (Configurazione generale).
    ?documento=<id> per un documento, ?ospite=<id> per tutti i documenti di un ospite (esportazione della cartella).
    """
    document = guest = None
    source = request.POST if request.method == "POST" else request.GET
    document_id, guest_id = source.get("documento", ""), source.get("ospite", "")
    if document_id.isdigit():
        document = get_object_or_404(Document.objects.select_related("guest"), pk=document_id)
        guest = document.guest
    elif guest_id.isdigit():
        guest = get_object_or_404(Guest, pk=guest_id)
    else:
        raise Http404
    next_url = source.get("next") or ""
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        next_url = document.get_absolute_url() if document else reverse("documents:guest_list", args=[guest.pk])
    if cie.has_document_access(request.user, guest, document):
        return redirect(next_url)
    error = None
    methods = cie.access_methods()
    if request.method == "POST":
        method = request.POST.get("metodo") if request.POST.get("metodo") in methods else methods[0]
        try:
            signature_request = cie.create_access_request(request.user, guest, document, method)
        except SignatureError as exc:
            error = str(exc)
        else:
            saved = request.session.get(ACCESS_NEXT, {})
            saved = dict(list(saved.items())[-20:])  # solo le ultime richieste
            saved[str(signature_request.pk)] = next_url
            request.session[ACCESS_NEXT] = saved
            return redirect("signatures:cie_request", request_id=signature_request.pk)
    enrollment = cie.enrollment_of(request.user)
    return render(request, "signatures/cie_access.html", {
        "document": document, "guest": guest, "next": next_url, "error": error,
        "can_use": cie.can_use_device(request.user), "devices": _devices(request.user),
        "fiscal_code": request.user.fiscal_code, "minutes": request.fasas_config.documents_cie_minutes,
        "allow_nis": "nis" in methods, "enrollment": enrollment,
        "cie_ready": bool(request.user.fiscal_code) and bool(external.trust_roots()),
    })


@require_POST
@permission_required("accounts.change_user", raise_exception=True)
def enrollment_action(request, pk):
    """Gestore del sistema: conferma la CIE registrata (dopo aver visto carta e persona) oppure la azzera."""
    from .models import CieEnrollment

    enrollment = get_object_or_404(CieEnrollment.objects.select_related("user"), pk=pk, revoked_at__isnull=True)
    try:
        if request.POST.get("action") == "confirm":
            cie.confirm_enrollment(enrollment, request.user)
            messages.success(request, f"CIE di {enrollment.user} confermata.")
        else:
            cie.revoke_enrollment(enrollment, request.user, "Azzerata dal gestore del sistema (es. PIN FASAS dimenticato)")
            messages.info(request, f"Registrazione della CIE di {enrollment.user} azzerata: dovrà registrarla di nuovo.")
    except SignatureError as exc:
        messages.error(request, str(exc))
    return redirect("accounts:user_list")


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
    if signature_request.purpose == SignatureRequest.Purpose.DOCUMENT:
        raise Http404
    signed = signature_request.status == SignatureRequest.Status.SIGNED
    if signature_request.purpose == SignatureRequest.Purpose.ACCEPTANCE and signed:
        raise Http404  # la copia firmata si scarica dal registro delle accettazioni
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


# --- Accettazione delle condizioni della FEA (DPCM 22/02/2013, art. 57) --------------------------------------

@require_POST
@permission_required("signatures.sign_with_cie", raise_exception=True)
def fea_accept(request):
    try:
        signature_request = cie.create_acceptance_request(request.user)
    except SignatureError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('signatures:credential')}#cie")
    return redirect("signatures:cie_request", request_id=signature_request.pk)


@require_POST
@permission_required("signatures.sign_with_cie", raise_exception=True)
def fea_revoke(request):
    acceptance = cie.valid_acceptance(request.user)
    if acceptance is not None:
        cie.revoke_acceptance(acceptance, request.user)
        messages.success(request, "Accettazione revocata: non puoi più firmare con la CIE finché non la firmi di nuovo. "
                                  "Le firme già apposte restano valide.")
    return redirect(f"{reverse('signatures:credential')}#cie")


def fea_file(request, pk):
    """Copia della dichiarazione firmata: per il firmatario sempre e gratuitamente, e per il registro."""
    acceptance = get_object_or_404(FEAAcceptance, pk=pk)
    if acceptance.user_id != request.user.pk and not request.user.has_perm("signatures.view_feaacceptance"):
        raise PermissionDenied
    log_event(AuditLog.Action.DOWNLOAD, acceptance)
    response = HttpResponse(read_encrypted(acceptance.signed_storage), content_type="application/pdf")
    name = f"accettazione_FEA_{acceptance.user.username}_{timezone.localtime(acceptance.accepted_at):%Y%m%d}.pdf"
    response["Content-Disposition"] = content_disposition_header(True, name)
    response["Cache-Control"] = "no-store"
    return response


@permission_required("signatures.view_feaacceptance", raise_exception=True)
def fea_registry(request):
    return render(request, "signatures/fea_registry.html", {
        "acceptances": FEAAcceptance.objects.select_related("user").all()[:500], "terms_draft": fea_terms.is_draft(),
        "retention_years": settings.FASAS_FEA_RETENTION_YEARS,
    })


def fea_characteristics(request):
    """Pagina pubblica (senza accesso): caratteristiche del sistema di FEA, da rendere note (art. 57, lett. e-f)."""
    version, _ = fea_terms.terms()
    return render(request, "signatures/fea_characteristics.html", {
        "community": cie._community(), "terms_version": version, "terms_draft": fea_terms.is_draft(),
        "timestamp": bool(settings.FASAS_SIGNATURE_TSA_URL) and settings.FASAS_CIE_TIMESTAMP,
    })
