import csv
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import FeedbackForm, FeedbackReplyForm
from .metrics import MAX_DAYS, default_period, pilot_metrics
from .models import Feedback


def _safe_page(request, value):
    """Solo il percorso di una pagina del FASAS, senza parametri (che potrebbero contenere ricerche o nomi)."""
    value = (value or "").split("?")[0].split("#")[0][:300]
    if value.startswith("/") and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}):
        return value
    return ""


@permission_required("feedback.add_feedback", raise_exception=True)
def create(request):
    page = _safe_page(request, request.POST.get("page") or request.GET.get("da"))
    form = FeedbackForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        feedback = form.save(commit=False)
        feedback.created_by = request.user
        feedback.role = request.user.get_role_display() if hasattr(request.user, "get_role_display") else ""
        feedback.page = page
        feedback.save()
        from fasas.notifications.services import notify

        notify("feedback", f"Nuova segnalazione: {feedback.get_kind_display().lower()}",
               f"Da {request.user.get_full_name() or request.user.username} ({feedback.role}).",
               link=reverse("feedback:list"))
        messages.success(request, "Grazie: segnalazione inviata. La pagina e l'ora sono state salvate insieme al testo.")
        return redirect(page or "core:dashboard")
    mine = Feedback.objects.filter(created_by=request.user)[:5]
    return render(request, "feedback/form.html", {"form": form, "page": page, "mine": mine})


@permission_required("feedback.view_feedback", raise_exception=True)
def feedback_list(request):
    status = request.GET.get("stato", "aperte")
    items = Feedback.objects.select_related("created_by", "handled_by")
    if status == "aperte":
        items = items.filter(status__in=Feedback.OPEN)
    elif status in Feedback.Status.values:
        items = items.filter(status=status)
    if request.GET.get("formato") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="segnalazioni.csv"'
        response.write("﻿")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Data", "Da", "Ruolo", "Pagina", "Tipo", "Testo", "Stato", "Risposta"])
        for f in items:
            writer.writerow([timezone.localtime(f.created_at).strftime("%d/%m/%Y %H:%M"), f.created_by, f.role, f.page,
                             f.get_kind_display(), f.text, f.get_status_display(), f.reply])
        return response
    return render(request, "feedback/list.html", {
        "items": items[:300], "status": status, "statuses": Feedback.Status.choices,
        "can_handle": request.user.has_perm("feedback.change_feedback"),
    })


@permission_required("feedback.change_feedback", raise_exception=True)
def handle(request, pk):
    feedback = get_object_or_404(Feedback, pk=pk)
    form = FeedbackReplyForm(request.POST or None, instance=feedback)
    if request.method == "POST" and form.is_valid():
        feedback = form.save(commit=False)
        feedback.handled_by = request.user
        feedback.handled_at = timezone.now()
        feedback.save()
        messages.success(request, "Segnalazione aggiornata.")
    return redirect(f"{reverse('feedback:list')}#s{pk}")


def _date(value, fallback):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


@permission_required("feedback.view_pilot_metrics", raise_exception=True)
def metrics_view(request):
    first, last = default_period()
    start, end = _date(request.GET.get("dal"), first), _date(request.GET.get("al"), last)
    if end < start:
        start, end = end, start
    end = min(end, timezone.localdate())
    if (end - start).days >= MAX_DAYS:
        start = end - datetime.timedelta(days=MAX_DAYS - 1)
        messages.info(request, f"Periodo ridotto agli ultimi {MAX_DAYS} giorni.")
    data = pilot_metrics(start, end)
    if request.GET.get("formato") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="indicatori-pilota-{start}-{end}.csv"'
        response.write("﻿")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["Giorno", "Turni chiusi", "Dosi programmate", "Registrate", "Mancanti", "In ritardo",
                         "Giro farmaci (min, mediana)", "Checklist %", "Segnalazioni"])
        for r in data["rows"]:
            writer.writerow([r["day"].strftime("%d/%m/%Y"), r["closed"], r["doses_total"], r["doses_documented"],
                             r["doses_missing"], r["doses_late"], r["round_median"] if r["round_median"] is not None else "",
                             r["checklist_pct"] if r["checklist_pct"] is not None else "", r["feedback"]])
        return response
    return render(request, "feedback/metrics.html", {"start": start, "end": end, **data})
