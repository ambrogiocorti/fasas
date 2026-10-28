from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import content_disposition_header

from fasas.guests.models import Guest

from .forms import GenerateReportForm, GuestExportForm
from .guest_export import build_guest_folder
from .models import GeneratedReport, ReportFormat, ReportType
from .services import generate_report, read_report, store_report


@permission_required("reports.view_generatedreport", raise_exception=True)
def report_list(request):
    reports = GeneratedReport.objects.select_related("guest", "generated_by", "schedule")
    if request.GET.get("type"):
        reports = reports.filter(report_type=request.GET["type"])
    if request.GET.get("guest"):
        reports = reports.filter(guest_id=request.GET["guest"])
    form = GenerateReportForm(request.POST or None)
    if request.method == "POST":
        if not request.user.has_perm("reports.add_generatedreport"):
            messages.error(request, "Non hai il permesso di generare report.")
        elif form.is_valid():
            data = form.cleaned_data
            report = generate_report(data["report_type"], data["format"], data["start"], data["end"],
                                     data["guest"], request.user)
            messages.success(request, f"Report «{report.title}» generato.")
            return redirect("reports:list")
    return render(request, "reports/list.html", {
        "reports": reports[:200], "form": form, "types": ReportType.choices,
    })


@permission_required("reports.view_generatedreport", raise_exception=True)
def report_download(request, pk):
    report = get_object_or_404(GeneratedReport, pk=pk)
    response = HttpResponse(read_report(report, request.user), content_type=report.content_type)
    response["Content-Disposition"] = content_disposition_header(True, report.filename)
    response["Cache-Control"] = "no-store"
    return response


@permission_required("guests.export_guest", raise_exception=True)
def guest_export(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    form = GuestExportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = build_guest_folder(guest, request.user, form.cleaned_data["include_documents"],
                                  form.cleaned_data["date_from"])
        report = store_report(data, f"Cartella completa {guest}", "guest_folder", ReportFormat.PDF, request.user,
                              guest, form.cleaned_data["date_from"], timezone.localdate())
        messages.success(request, "Cartella esportata. Il file resta disponibile nell'archivio report.")
        return redirect("reports:download", pk=report.pk)
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": f"Esporta cartella completa – {guest}",
        "submit_label": "Genera PDF", "cancel_url": guest.get_absolute_url(),
        "intro": "Genera un unico PDF con dati anagrafici e sanitari, PAI, terapie, eventi e documenti: "
                 "da consegnare quando l'ospite cambia struttura. L'esportazione è registrata nell'audit log.",
    })
