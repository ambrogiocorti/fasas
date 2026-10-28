from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.guests.models import Guest

from .forms import DocumentEditForm, DocumentForm, VersionForm
from .models import Document, DocumentVersion
from .services import add_uploaded_version, create_document, read_version

INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/gif", "text/plain"}


@permission_required("documents.view_document", raise_exception=True)
def guest_documents(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    documents = guest.documents.prefetch_related("versions")
    category = request.GET.get("category")
    if category:
        documents = documents.filter(category=category)
    return render(request, "documents/guest_documents.html", {
        "guest": guest, "documents": documents, "categories": Document.Category.choices, "category": category,
        "active_tab": "documents",
    })


@permission_required("documents.add_document", raise_exception=True)
def document_create(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    if guest.is_archived:
        messages.error(request, "Cartella archiviata: non è possibile caricare documenti.")
        return redirect(guest.get_absolute_url())
    form = DocumentForm(request.POST or None, request.FILES or None, initial={"category": request.GET.get("category")})
    if request.method == "POST" and form.is_valid():
        data = {k: form.cleaned_data[k] for k in ("description", "document_date", "expires_on")}
        document = create_document(
            guest, form.cleaned_data["category"], form.cleaned_data["title"],
            uploaded=form.cleaned_data["file"], user=request.user, **data,
        )
        messages.success(request, "Documento caricato e cifrato.")
        return redirect(document.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": "Carica documento", "multipart": True,
        "cancel_url": guest.get_absolute_url(),
    })


@permission_required("documents.view_document", raise_exception=True)
def document_detail(request, pk):
    document = get_object_or_404(Document.objects.select_related("guest"), pk=pk)
    versions = document.versions.select_related("uploaded_by").prefetch_related("signatures_requested")
    access_log = None
    if request.user.has_perm("audit.view_auditlog") or request.user.has_perm("guests.change_guest"):
        ct = ContentType.objects.get_for_model(DocumentVersion)
        access_log = AuditLog.objects.filter(
            content_type=ct, object_id__in=[str(v.pk) for v in versions]
        ).order_by("-timestamp")[:50]
    return render(request, "documents/document_detail.html", {
        "document": document, "guest": document.guest, "versions": versions, "access_log": access_log,
        "version_form": VersionForm(), "active_tab": "documents",
    })


@permission_required("documents.change_document", raise_exception=True)
def document_edit(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if document.guest.is_archived:
        raise PermissionDenied("Cartella archiviata.")
    form = DocumentEditForm(request.POST or None, instance=document)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Documento aggiornato.")
        return redirect(document.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": document.guest, "page_title": f"Modifica {document}",
        "cancel_url": document.get_absolute_url(),
    })


@permission_required("documents.add_document", raise_exception=True)
def version_upload(request, pk):
    document = get_object_or_404(Document, pk=pk)
    form = VersionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        version = add_uploaded_version(document, form.cleaned_data["file"], request.user, form.cleaned_data["note"])
        messages.success(request, f"Caricata la versione {version.number}.")
        return redirect(document.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": document.guest, "page_title": f"Nuova versione di {document}", "multipart": True,
        "cancel_url": document.get_absolute_url(),
    })


def _file_response(request, version, inline):
    if not request.user.has_perm("documents.view_document"):
        raise PermissionDenied
    data = read_version(version, user=request.user, audit=not inline)
    if inline:
        log_event(AuditLog.Action.VIEW, version, guest=version.document.guest)
    content_type = version.content_type if inline and version.content_type in INLINE_TYPES else "application/octet-stream"
    response = HttpResponse(data, content_type=content_type if inline else version.content_type)
    response["Content-Disposition"] = content_disposition_header(not inline, version.original_name)
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def version_download(request, pk):
    return _file_response(request, get_object_or_404(DocumentVersion, pk=pk), inline=False)


def version_view(request, pk):
    return _file_response(request, get_object_or_404(DocumentVersion, pk=pk), inline=True)
