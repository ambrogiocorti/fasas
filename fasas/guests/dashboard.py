"""Dashboard clinica dell'ospite (sezione 12) e storico completo (sezione 13)."""
import datetime

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone


def clinical_dashboard(guest):
    from fasas.appointments.models import Appointment
    from fasas.clinical.models import ClinicalEvent, Restraint, Therapy, TherapyAdministration
    from fasas.clinical.services import latest_parameters, recent_parameters
    from fasas.daily.models import DiaryEntry
    from fasas.daily.services import days_since_last_evacuation
    from fasas.pai.models import PAI
    from fasas.protocols.engine import open_activations

    now = timezone.now()
    week_ago = now - datetime.timedelta(days=7)
    therapies = guest.therapies.filter(status=Therapy.Status.ACTIVE).select_related("drug")
    days, last_evac = days_since_last_evacuation(guest)
    return {
        "therapies": [t for t in therapies if not t.is_sos],
        "sos_therapies": [t for t in therapies if t.is_sos],
        "latest_parameters": latest_parameters(guest),
        "recent_parameters": recent_parameters(guest, 7)[:30],
        "protocols": open_activations(guest),
        "events": ClinicalEvent.objects.filter(guest=guest, occurred_at__gte=now - datetime.timedelta(days=14))[:10],
        "allergies": guest.allergies.all(),
        "diagnoses": guest.diagnoses.filter(active=True),
        "tag_alerts": [t for t in guest.tags.all() if t.alert_message],
        "active_restraints": Restraint.objects.filter(guest=guest, ended_at__isnull=True),
        "appointments": Appointment.objects.filter(
            guest=guest, status=Appointment.Status.SCHEDULED, scheduled_at__gte=now - datetime.timedelta(hours=2)
        )[:5],
        "diary": DiaryEntry.objects.filter(guest=guest, occurred_at__gte=week_ago).select_related("created_by")[:5],
        "sos_week": TherapyAdministration.objects.filter(guest=guest, is_sos=True, occurred_at__gte=week_ago).count(),
        "days_since_evacuation": days,
        "last_evacuation": last_evac,
        "pai": PAI.objects.filter(guest=guest, status=PAI.Status.ACTIVE).first(),
        "emergency_contacts": guest.contacts.filter(is_emergency_contact=True),
    }


TIMELINE_KINDS = [
    ("movement", "Ingressi e movimenti"),
    ("therapy", "Terapie"),
    ("event", "Eventi sanitari"),
    ("restraint", "Contenzioni"),
    ("protocol", "Protocolli"),
    ("document", "Documenti"),
    ("pai", "PAI"),
    ("appointment", "Visite"),
    ("report", "Report ed esportazioni"),
]


def _therapy_changes(guest):
    from fasas.audit.models import AuditLog
    from fasas.clinical.models import Therapy

    ct = ContentType.objects.get_for_model(Therapy)
    therapies = {t.pk: t for t in guest.therapies.select_related("drug")}
    labels = {f.name: f.verbose_name for f in Therapy._meta.fields}
    for entry in AuditLog.objects.filter(content_type=ct, guest_id=guest.pk).order_by("-timestamp")[:300]:
        therapy = therapies.get(int(entry.object_id)) if entry.object_id.isdigit() else None
        if entry.action == AuditLog.Action.CREATE:
            title = f"Nuova terapia: {therapy or entry.object_repr}"
            detail = ""
        else:
            title = f"Terapia modificata: {therapy or entry.object_repr}"
            detail = "; ".join(
                f"{labels.get(k, k)}: {v[0] if v[0] not in (None, '') else '—'} → {v[1] if v[1] not in (None, '') else '—'}"
                for k, v in entry.changes.items() if k not in ("conflict_acknowledged",)
            )
        if entry.reason:
            detail = f"{detail} (motivo: {entry.reason})".strip()
        yield {
            "when": entry.timestamp, "kind": "therapy", "title": title, "detail": detail, "user": entry.username,
            "url": therapy.get_absolute_url() if therapy else "",
        }


TIMELINE_PERMISSIONS = {
    "movement": "guests.view_admissionevent",
    "therapy": "clinical.view_therapy",
    "event": "clinical.view_clinicalevent",
    "restraint": "clinical.view_restraint",
    "protocol": "protocols.view_protocolactivation",
    "document": "documents.view_document",
    "pai": "pai.view_pai",
    "appointment": "appointments.view_appointment",
    "report": "reports.view_generatedreport",
}


def timeline_kinds_for(user):
    return [(code, label) for code, label in TIMELINE_KINDS if user.has_perm(TIMELINE_PERMISSIONS[code])]


def timeline(guest, kinds=None, limit=400):
    from fasas.clinical.models import ClinicalEvent, Restraint
    from fasas.documents.models import DocumentVersion
    from fasas.reports.models import GeneratedReport

    items = []
    wanted = set(kinds or [k for k, _ in TIMELINE_KINDS])

    def at(day):
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(12, 0)))

    if "movement" in wanted:
        for m in guest.admission_events.all():
            items.append({"when": at(m.date), "kind": "movement", "title": m.get_kind_display(), "detail": m.notes,
                          "user": str(m.created_by or ""), "url": ""})
        if not guest.admission_events.filter(kind="admission").exists():
            items.append({"when": at(guest.admission_date), "kind": "movement", "title": "Ingresso in struttura",
                          "detail": "", "user": "", "url": ""})
    if "therapy" in wanted:
        items.extend(_therapy_changes(guest))
    if "event" in wanted:
        for e in ClinicalEvent.all_objects.filter(guest=guest).select_related("created_by"):
            items.append({"when": e.occurred_at, "kind": "event",
                          "title": f"{e.get_event_type_display()} ({e.get_severity_display().lower()})"
                                   + (" – ANNULLATO" if e.is_voided else ""),
                          "detail": e.description[:200], "user": str(e.created_by or ""),
                          "url": reverse("clinical:event_detail", args=[e.pk])})
    if "restraint" in wanted:
        for r in Restraint.all_objects.filter(guest=guest).select_related("responsible_operator"):
            items.append({"when": r.occurred_at, "kind": "restraint",
                          "title": f"Contenzione: {r.get_restraint_type_display()}",
                          "detail": f"{r.reason[:150]} – durata {r.duration_display}",
                          "user": str(r.responsible_operator), "url": reverse("clinical:guest_events", args=[guest.pk])})
    if "protocol" in wanted:
        for a in guest.protocol_activations.select_related("protocol"):
            items.append({"when": a.triggered_at, "kind": "protocol", "title": f"Protocollo attivato: {a.protocol.name}",
                          "detail": f"{a.trigger_summary} – {a.get_status_display()}", "user": "sistema",
                          "url": a.get_absolute_url()})
    if "document" in wanted:
        for v in DocumentVersion.objects.filter(document__guest=guest).select_related("document", "uploaded_by"):
            items.append({"when": v.uploaded_at, "kind": "document",
                          "title": f"Documento {'firmato' if v.is_signed else 'caricato'}: {v.document.title} (v{v.number})",
                          "detail": v.document.get_category_display(), "user": str(v.uploaded_by),
                          "url": v.document.get_absolute_url()})
    if "pai" in wanted:
        for p in guest.pais.select_related("approved_by"):
            if p.approved_at:
                items.append({"when": p.approved_at, "kind": "pai", "title": f"PAI v{p.version} in vigore",
                              "detail": f"Revisione entro il {p.review_due:%d/%m/%Y}", "user": str(p.approved_by or ""),
                              "url": p.get_absolute_url()})
    if "appointment" in wanted:
        for a in guest.appointments.exclude(status="scheduled"):
            items.append({"when": a.scheduled_at, "kind": "appointment",
                          "title": f"{a.get_kind_display()}: {a.title} ({a.get_status_display().lower()})",
                          "detail": a.outcome[:200], "user": a.companion_display, "url": a.get_absolute_url()})
    if "report" in wanted:
        for r in GeneratedReport.objects.filter(guest=guest).select_related("generated_by"):
            items.append({"when": r.generated_at, "kind": "report", "title": f"Generato: {r.title}", "detail": "",
                          "user": str(r.generated_by or "sistema"), "url": reverse("reports:download", args=[r.pk])})
    items.sort(key=lambda i: i["when"], reverse=True)
    return items[:limit]
