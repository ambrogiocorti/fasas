from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render

from fasas.documents.models import DocumentVersion
from fasas.documents.services import read_version

from .forms import CredentialForm, RemoteCredentialForm, SignForm
from .models import SigningCredential
from .providers import SignatureError, verify_pdf
from .services import register_pkcs12, sign_version


@permission_required("signatures.sign_document", raise_exception=True)
def credential_view(request):
    credential = SigningCredential.objects.filter(user=request.user).first()
    form = CredentialForm(request.POST or None, request.FILES or None, prefix="p12")
    remote_form = RemoteCredentialForm(request.POST or None, prefix="remote")
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
            credential, _ = SigningCredential.objects.get_or_create(user=request.user)
            credential.kind = SigningCredential.Kind.REMOTE
            credential.remote_user_id = remote_form.cleaned_data["remote_user_id"]
            credential.certificate_subject = remote_form.cleaned_data["certificate_subject"]
            credential.save()
            messages.success(request, "Firma remota configurata.")
            return redirect("signatures:credential")
    return render(request, "signatures/credential.html", {
        "credential": credential, "form": form, "remote_form": remote_form,
    })


@permission_required("signatures.sign_document", raise_exception=True)
def sign_version_view(request, pk):
    version = get_object_or_404(DocumentVersion.objects.select_related("document__guest"), pk=pk)
    form = SignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            signature = sign_version(version, request.user, form.cleaned_data["secret"], form.cleaned_data["reason"])
        except SignatureError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Documento firmato: creata la versione {signature.signed_version.number}.")
            return redirect(version.document.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": version.document.guest, "page_title": f"Firma digitale – {version}",
        "submit_label": "Firma", "cancel_url": version.document.get_absolute_url(),
        "intro": "La firma PAdES viene apposta al PDF e genera una nuova versione del documento. "
                 "La versione originale resta archiviata.",
    })


@permission_required("documents.view_document", raise_exception=True)
def verify_version_view(request, pk):
    version = get_object_or_404(DocumentVersion.objects.select_related("document__guest"), pk=pk)
    results = verify_pdf(read_version(version, user=request.user)) if version.is_pdf else []
    return render(request, "signatures/verify.html", {
        "version": version, "document": version.document, "guest": version.document.guest, "results": results,
    })
