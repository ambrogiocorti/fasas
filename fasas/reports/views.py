from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header

from fasas.documents.cie_gate import cie_gate
from fasas.guests.models import Guest

from .forms import GenerateReportForm, GuestExportForm
from .guest_export import build_guest_folder
from .models import GeneratedReport, ReportFormat, ReportType
from .services import generate_any, read_report, store_report


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
            reports = generate_any(data["report_type"], data["template"], data["format"], data["start"], data["end"],
                                   data["guest"], request.user)
            messages.success(request, f"Report «{reports[0].title}» generato"
                                      f"{' in PDF ed Excel' if len(reports) > 1 else ''}.")
            return redirect("reports:list")
    return render(request, "reports/list.html", {
        "reports": reports[:200], "form": form, "types": ReportType.choices + [("custom", "Report da modello")],
    })


@permission_required("reports.view_generatedreport", raise_exception=True)
def report_download(request, pk):
    report = get_object_or_404(GeneratedReport, pk=pk)
    if report.report_type == "guest_folder" and report.guest_id:  # contiene i documenti dell'ospite
        if (gate := cie_gate(request, report.guest)) is not None:
            return gate
    response = HttpResponse(read_report(report, request.user), content_type=report.content_type)
    response["Content-Disposition"] = content_disposition_header(True, report.filename)
    response["Cache-Control"] = "no-store"
    return response


@permission_required("guests.export_guest", raise_exception=True)
def guest_export(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    form = GuestExportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["include_documents"] and (gate := cie_gate(request, guest)) is not None:
            return gate
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


@permission_required("reports.add_generatedreport", raise_exception=True)
def inspection(request):
    """Pacchetto «pronto per l'ispezione»: un PDF con la situazione di oggi e i dati del periodo, archiviato come i
    report (cifrato, con la stessa conservazione) e registrato nell'audit."""
    import datetime

    from .forms import InspectionForm
    from .inspection import build_inspection

    today = timezone.localdate()
    form = InspectionForm(request.POST or None, initial={"start": today - datetime.timedelta(days=29), "end": today})
    if request.method == "POST" and form.is_valid():
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        data = build_inspection(start, end, request.user)
        report = store_report(data, "Pacchetto per l'ispezione", "inspection", ReportFormat.PDF, request.user,
                              None, start, end)
        messages.success(request, "Pacchetto generato: resta disponibile nell'archivio report.")
        return redirect("reports:download", pk=report.pk)
    return render(request, "generic/form.html", {
        "form": form, "page_title": "Pacchetto per l'ispezione", "submit_label": "Genera PDF",
        "cancel_url": reverse("reports:list"),
        "intro": "Un unico PDF per la vigilanza ATS/ASL: ospiti in carico con lo stato del PAI, terapie e "
                 "somministrazioni del periodo, eventi gravi e cadute, contenzioni, valutazioni e lesioni, farmaci "
                 "scaduti, protocolli, documenti in scadenza, backup e verifica del registro delle operazioni. "
                 "Contiene dati sanitari: va consegnato solo a chi effettua l'ispezione.",
    })


@permission_required("reports.view_quality_indicators", raise_exception=True)
def quality(request):
    """Indicatori di qualità degli ultimi 12 mesi, per il coordinatore (e il medico), con esportazione CSV."""
    from . import quality as indicators

    data = indicators.monthly()
    if request.GET.get("formato") == "csv":
        response = HttpResponse(indicators.export_csv(data), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="indicatori-qualita-{data["today"]:%Y%m%d}.csv"'
        return response
    return render(request, "reports/quality.html", data)
