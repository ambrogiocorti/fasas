"""Ricerca globale (sezione 23): ospiti, farmaci/terapie, eventi, documenti, protocolli, diario, appuntamenti."""
import datetime

from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse

from fasas.accounts.models import User
from fasas.guests.models import Guest

SECTIONS = [
    ("guests", "Ospiti"),
    ("therapies", "Farmaci e terapie"),
    ("events", "Eventi sanitari"),
    ("documents", "Documenti"),
    ("protocols", "Protocolli"),
    ("diary", "Diario e registro"),
    ("appointments", "Appuntamenti"),
]


def _date(value):
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def search(request):
    from fasas.appointments.models import Appointment
    from fasas.clinical.models import ClinicalEvent, Therapy
    from fasas.daily.models import DailyRecord, DiaryEntry
    from fasas.documents.models import Document
    from fasas.protocols.models import ProtocolActivation

    p = request.GET
    q = p.get("q", "").strip()
    section = p.get("type", "")
    date_from, date_to = _date(p.get("date_from")), _date(p.get("date_to"))
    guest_id = p.get("guest") or None
    operator_id = p.get("operator") or None
    user = request.user
    results = {}

    def dated(qs, field):
        if date_from:
            qs = qs.filter(**{f"{field}__date__gte" if field.endswith("_at") else f"{field}__gte": date_from})
        if date_to:
            qs = qs.filter(**{f"{field}__date__lte" if field.endswith("_at") else f"{field}__lte": date_to})
        return qs

    def scoped(qs, guest_field="guest_id", operator_field="created_by_id"):
        if guest_id:
            qs = qs.filter(**{guest_field: guest_id})
        if operator_id and operator_field:
            qs = qs.filter(**{operator_field: operator_id})
        return qs

    def wanted(name, perm):
        return (not section or section == name) and user.has_perm(perm)

    has_filters = q or date_from or date_to or guest_id or operator_id
    if has_filters:
        if wanted("guests", "guests.view_guest") and q:
            qs = Guest.objects.filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(fiscal_code__icontains=q)
                | Q(room__icontains=q) | Q(tags__name__icontains=q) | Q(diagnoses__description__icontains=q)
            ).distinct()
            results["guests"] = [{"title": str(g), "subtitle": f"CF {g.fiscal_code} · {g.get_status_display()}",
                                  "url": g.get_absolute_url()} for g in scoped(qs, "pk", None)[:50]]
        if wanted("therapies", "clinical.view_therapy"):
            qs = Therapy.objects.select_related("drug", "guest")
            if q:
                qs = qs.filter(Q(drug__name__icontains=q) | Q(drug__active_ingredient__icontains=q)
                               | Q(drug__atc_code__icontains=q) | Q(sos_indication__icontains=q))
            qs = dated(scoped(qs), "start_date")
            results["therapies"] = [{"title": f"{t.drug} – {t.guest}",
                                     "subtitle": f"{t.dose_display} · {t.get_status_display()} · dal {t.start_date:%d/%m/%Y}",
                                     "url": t.get_absolute_url()} for t in qs[:50]]
        if wanted("events", "clinical.view_clinicalevent"):
            qs = ClinicalEvent.objects.select_related("guest", "created_by")
            if q:
                qs = qs.filter(Q(description__icontains=q) | Q(actions_taken__icontains=q) | Q(event_type__icontains=q))
            qs = dated(scoped(qs), "occurred_at")
            results["events"] = [{"title": str(e), "subtitle": e.description[:140],
                                  "url": reverse("clinical:event_detail", args=[e.pk])} for e in qs[:50]]
        if wanted("documents", "documents.view_document"):
            qs = Document.objects.select_related("guest")
            if q:
                qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                               | Q(versions__original_name__icontains=q)).distinct()
            qs = dated(scoped(qs), "created_at")
            results["documents"] = [{"title": f"{d.title} – {d.guest}", "subtitle": d.get_category_display(),
                                     "url": d.get_absolute_url()} for d in qs[:50]]
        if wanted("protocols", "protocols.view_protocolactivation"):
            qs = ProtocolActivation.objects.select_related("guest", "protocol")
            if q:
                qs = qs.filter(Q(protocol__name__icontains=q) | Q(trigger_summary__icontains=q)
                               | Q(resolution_notes__icontains=q))
            qs = dated(scoped(qs, operator_field="resolved_by_id"), "triggered_at")
            results["protocols"] = [{"title": str(a), "subtitle": f"{a.trigger_summary} · {a.get_status_display()}",
                                     "url": a.get_absolute_url()} for a in qs[:50]]
        if wanted("diary", "daily.view_diaryentry"):
            diary = DiaryEntry.objects.select_related("guest", "created_by")
            records = DailyRecord.objects.select_related("guest", "created_by")
            if q:
                diary = diary.filter(text__icontains=q)
                records = records.filter(description__icontains=q)
            diary = dated(scoped(diary), "occurred_at")
            records = dated(scoped(records), "occurred_at")
            items = [{"title": f"Diario – {d.guest} – {d.occurred_at:%d/%m/%Y}", "subtitle": d.text[:160],
                      "url": reverse("daily:guest_diary", args=[d.guest_id]), "when": d.occurred_at} for d in diary[:50]]
            items += [{"title": f"{r.get_category_display()} – {r.guest}", "subtitle": r.description[:160],
                       "url": reverse("daily:guest_daily", args=[r.guest_id]), "when": r.occurred_at} for r in records[:50]]
            results["diary"] = sorted(items, key=lambda i: i["when"], reverse=True)[:80]
        if wanted("appointments", "appointments.view_appointment"):
            qs = Appointment.objects.select_related("guest")
            if q:
                qs = qs.filter(Q(title__icontains=q) | Q(doctor__icontains=q) | Q(location__icontains=q)
                               | Q(outcome__icontains=q))
            qs = dated(scoped(qs), "scheduled_at")
            results["appointments"] = [{"title": str(a), "subtitle": a.get_status_display(),
                                        "url": a.get_absolute_url()} for a in qs[:50]]

    ordered = [(key, label, results[key]) for key, label in SECTIONS if key in results]
    return render(request, "search/results.html", {
        "q": q, "sections": SECTIONS, "section": section, "results": ordered,
        "total": sum(len(r) for _, _, r in ordered), "has_filters": has_filters,
        "guests": Guest.objects.all(), "operators": User.objects.filter(is_active=True),
        "params": p,
    })
