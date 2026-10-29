import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from fasas.core.encryption import DecryptionError, decrypt, encrypt
from fasas.documents.models import DocumentVersion
from fasas.documents.services import read_version

from .forms import CredentialForm, RemoteCredentialForm, SendOTPForm, SignForm
from .models import SigningCredential
from .providers import SignatureError, signature_level, verify_pdf
from .services import register_pkcs12, register_remote, request_otp, sign_version

TOKEN_KEY = "fasas_csc_token"
TOKEN_MINUTES = 5


@permission_required("signatures.sign_document", raise_exception=True)
def credential_view(request):
    credential = SigningCredential.objects.filter(user=request.user).first()
    form = CredentialForm(request.POST or None, request.FILES or None, prefix="p12")
    remote_form = RemoteCredentialForm(request.POST or None, prefix="remote",
                                       initial={"remote_user_id": getattr(credential, "remote_user_id", "")})
    if request.method == "POST":
        if "p12-certificate" in request.FILES and form.is_valid():
            try:
                register_pkcs12(request.user, form.cleaned_data["certificate"].read(), form.cleaned_data["passphrase"])
            except SignatureError as exc:
                form.add_error("passphrase", str(exc))
            else:
                messages.success(request, "Certificato di firma registrato e cifrato.")
                return redirect("signatures:credential")
        elif "remote-remote_user_id" in request.POST and remote_form.is_valid():
            data = remote_form.cleaned_data
            try:
                register_remote(request.user, data["remote_user_id"], data["password"], data["credential_id"])
            except SignatureError as exc:
                remote_form.add_error(None, str(exc))
            else:
                messages.success(request, "Firma remota collegata: certificato letto dal prestatore.")
                return redirect("signatures:credential")
    try:
        level, level_error = signature_level(), ""
    except SignatureError as exc:
        level, level_error = "", str(exc)
    return render(request, "signatures/credential.html", {
        "credential": credential, "form": form, "remote_form": remote_form,
        "remote_configured": bool(settings.FASAS_CSC_SERVICE_URL), "provider_name": settings.FASAS_CSC_PROVIDER_NAME,
        "level": level, "level_error": level_error, "tsa": bool(settings.FASAS_SIGNATURE_TSA_URL),
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
