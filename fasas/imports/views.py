from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST

from fasas.guests.models import Guest

from . import documents as document_import
from .forms import DocumentsForm, WorkbookForm
from .models import ImportBatch
from .services import close_workbook, run_workbook_import, store_workbook, workbook_bytes
from .spec import SHEETS
from .template import build_template

PERM = "imports.add_importbatch"


@permission_required(PERM, raise_exception=True)
def home(request):
    return render(request, "imports/home.html", {
        "workbook_form": WorkbookForm(), "documents_form": DocumentsForm(), "sheets": SHEETS,
        "batches": ImportBatch.objects.select_related("created_by")[:30],
    })


@permission_required(PERM, raise_exception=True)
def template_download(request):
    response = HttpResponse(build_template(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = content_disposition_header(True, "FASAS - modello importazione.xlsx")
    return response


@require_POST
@permission_required(PERM, raise_exception=True)
def workbook_upload(request):
    form = WorkbookForm(request.POST, request.FILES)
    if not form.is_valid():
        for error in form.errors.get("file", []):
            messages.error(request, error)
        return redirect("imports:home")
    uploaded = form.cleaned_data["file"]
    data = uploaded.read()
    report = run_workbook_import(data, request.user, commit=False, filename=uploaded.name)
    batch = store_workbook(data, uploaded.name, request.user, report)
    return redirect("imports:batch", pk=batch.pk)


@require_POST
@permission_required("documents.add_document", raise_exception=True)
@permission_required(PERM, raise_exception=True)
def documents_upload(request):
    form = DocumentsForm(request.POST, request.FILES)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("imports:home")
    try:
        batch = document_import.prepare_from_upload(request.FILES.getlist("files"), request.user,
                                                    form.cleaned_data["category"], form.cleaned_data["document_date"])
    except document_import.DocumentImportError as exc:
        messages.error(request, str(exc))
        return redirect("imports:home")
    return redirect("imports:batch", pk=batch.pk)


@permission_required(PERM, raise_exception=True)
def batch_detail(request, pk):
    batch = get_object_or_404(ImportBatch.objects.select_related("created_by"), pk=pk)
    context = {"batch": batch}
    if batch.kind == ImportBatch.Kind.WORKBOOK:
        issues = batch.summary.get("issues", [])
        context.update({
            "counts": [(s.name, s.title, batch.summary.get("counts", {}).get(s.name, {})) for s in SHEETS],
            "errors": [i for i in issues if i["level"] == "error"],
            "warnings": [i for i in issues if i["level"] == "warning"],
        })
    else:
        guests = Guest.objects.exclude(status=Guest.Status.ARCHIVED).order_by("last_name", "first_name")
        context.update({
            "entries": list(enumerate(batch.payload)), "guests": guests,
            "matched": sum(1 for e in batch.payload if e.get("guest_id") and not e["problem"]),
            "category_label": dict(DocumentsForm.base_fields["category"].choices).get(batch.summary.get("category")),
        })
    return render(request, "imports/batch.html", context)


@require_POST
@permission_required(PERM, raise_exception=True)
def batch_confirm(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, status=ImportBatch.Status.PREVIEW)
    if batch.created_by_id != request.user.pk:
        messages.error(request, "Solo chi ha caricato il file può confermare l'importazione.")
        return redirect("imports:batch", pk=pk)
    if batch.kind == ImportBatch.Kind.WORKBOOK:
        report = run_workbook_import(workbook_bytes(batch), request.user, commit=True, filename=batch.filename)
        if report.committed:
            close_workbook(batch, ImportBatch.Status.COMPLETED, report)
            messages.success(request, f"Importazione completata: {report.total_created} voci inserite.")
        else:
            batch.summary = report.as_dict()
            batch.save(update_fields=["summary"])
            messages.error(request, "Nel frattempo sono cambiati alcuni dati: correggere gli errori e ricaricare il file.")
    else:
        if not request.user.has_perm("documents.add_document"):
            messages.error(request, "Non hai il permesso di caricare documenti.")
            return redirect("imports:batch", pk=pk)
        choices = {}
        for index, entry in enumerate(batch.payload):
            if entry["problem"]:
                continue
            guest_id = request.POST.get(f"guest_{index}", "")
            include = request.POST.get(f"include_{index}") == "on"
            title = request.POST.get(f"title_{index}", entry["title"]).strip()[:200] or entry["title"]
            choices[index] = (int(guest_id) if include and guest_id.isdigit() else None, title)
        try:
            created, skipped = document_import.confirm_batch(batch, request.user, choices)
        except document_import.DocumentImportError as exc:
            messages.error(request, str(exc))
            return redirect("imports:batch", pk=pk)
        messages.success(request, f"{created} documenti caricati nelle cartelle"
                                  + (f", {skipped} scartati." if skipped else "."))
    return redirect("imports:batch", pk=pk)


@require_POST
@permission_required(PERM, raise_exception=True)
def batch_cancel(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, status=ImportBatch.Status.PREVIEW)
    if batch.kind == ImportBatch.Kind.WORKBOOK:
        close_workbook(batch, ImportBatch.Status.CANCELLED)
    else:
        document_import.cancel_batch(batch)
    messages.info(request, "Importazione annullata: i file caricati sono stati cancellati.")
    return redirect("imports:home")
