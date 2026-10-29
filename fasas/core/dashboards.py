"""
Cruscotti per ruolo (spec. §2). Ogni ruolo vede ciò che deve fare, non tutto il sistema:

- operatore: il turno in corso (farmaci, checklist, evacuazioni, protocolli da eseguire, consegne);
- coordinatore: la supervisione della struttura (validazioni, eventi gravi, turni, PAI, scorte);
- medico: terapie, SOS da validare, parametri fuori norma, contenzioni, documenti da firmare;
- amministratore: lo stato del sistema (utenti, accessi, backup, audit, configurazione), senza dati clinici.
"""
import datetime

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import SystemConfig
from .shifts import Shift, previous_shift, resolve_shift, shift_bounds


def _shift_context(user):
    from fasas.daily.models import ShiftAssignment
    from fasas.daily.services import is_shift_closed

    day, shift = resolve_shift()
    start, end = shift_bounds(day, shift)
    return {
        "day": day, "shift": shift, "shift_label": Shift(shift).label, "shift_start": start, "shift_end": end,
        "shift_closed": is_shift_closed(day, shift),
        "on_shift": ShiftAssignment.objects.filter(date=day, shift=shift).select_related("user"),
        "checked_in": ShiftAssignment.objects.filter(date=day, shift=shift, user=user, checked_in_at__isnull=False).exists(),
    }


def _protocols_with_actions(limit=10):
    from fasas.protocols.engine import open_activations

    rows = []
    for activation in open_activations().prefetch_related("action_logs")[:limit]:
        actions = activation.actions_status()
        rows.append({"activation": activation, "pending": sum(1 for a in actions if not a["log"]),
                     "total": len(actions)})
    return rows


def _guest_counts():
    from fasas.guests.models import Guest

    return {
        "guest_count": Guest.objects.filter(status=Guest.Status.ACTIVE).count(),
        "absent_count": Guest.objects.filter(status=Guest.Status.HOSPITALIZED).count(),
    }


def operator(request):
    from fasas.appointments.models import Appointment
    from fasas.clinical.services import scheduled_doses
    from fasas.daily.models import DiaryEntry, EvacuationRecord, ShiftClosure
    from fasas.daily.services import checklist_status, evacuation_overview
    from fasas.guests.models import Guest
    from fasas.guests.services import guests_in_care
    from fasas.notifications.services import unread_for
    from fasas.protocols.models import Protocol

    user = request.user
    ctx = _shift_context(user) | _guest_counts()
    day, shift = ctx["day"], ctx["shift"]
    now = timezone.now()
    today = timezone.localdate()
    config = SystemConfig.get()
    present = guests_in_care().filter(status=Guest.Status.ACTIVE)

    doses = scheduled_doses(day, shift, guests_in_care())
    status = checklist_status(day, shift)
    protocol = Protocol.objects.filter(kind=Protocol.Kind.EVACUATION, active=True).first()
    threshold = int((protocol.params or {}).get("days", 3)) if protocol else 3
    recorded = set(EvacuationRecord.objects.filter(shift_date=today).values_list("guest_id", flat=True))
    evacuations = evacuation_overview(present, today)
    prev_day, prev_shift = previous_shift(day, shift)
    handover = ShiftClosure.objects.filter(date=prev_day, shift=prev_shift).select_related("closed_by").first()

    ctx.update({
        "doses_total": len(doses), "doses_done": sum(1 for d in doses if d.done),
        "doses_due": [d for d in doses if not d.done and d.moment <= now + datetime.timedelta(minutes=60)],
        "checklist_total": status["total"], "checklist_done": status["done"],
        "protocols": _protocols_with_actions(),
        "evacuation_mode": config.evacuation_mode,
        "evacuation_alerts": [r for r in evacuations if r["days"] >= threshold],
        "evacuation_missing": [r["guest"] for r in evacuations if r["guest"].pk not in recorded]
        if config.evacuation_mode == SystemConfig.EvacuationMode.DAILY else [],
        "handover": handover,
        "appointments_today": Appointment.objects.filter(
            status=Appointment.Status.SCHEDULED, scheduled_at__date=today).select_related("guest", "companion"),
        "guests": present,
        "relevant_diary": DiaryEntry.objects.filter(is_relevant=True, occurred_at__gte=now - datetime.timedelta(hours=24))
        .select_related("guest", "created_by")[:5],
        "notifications": unread_for(user)[:5],
    })
    return ctx


def coordinator(request):
    from fasas.appointments.models import Appointment
    from fasas.clinical.models import ClinicalEvent, Restraint, Therapy, TherapyAdministration
    from fasas.clinical.services import scheduled_doses
    from fasas.daily.models import ShiftClosure
    from fasas.daily.services import checklist_status
    from fasas.documents.models import Document
    from fasas.guests.services import guests_in_care
    from fasas.pai.models import PAI
    from fasas.pharmacy.services import drug_stock_summary

    user = request.user
    ctx = _shift_context(user) | _guest_counts()
    day, shift = ctx["day"], ctx["shift"]
    now = timezone.now()
    today = timezone.localdate()
    config = SystemConfig.get()

    doses = scheduled_doses(day, shift, guests_in_care())
    status = checklist_status(day, shift)
    stock = drug_stock_summary()
    in_care = guests_in_care()
    with_pai = set(PAI.objects.filter(status=PAI.Status.ACTIVE).values_list("guest_id", flat=True))

    recent_days = [today - datetime.timedelta(days=i) for i in range(3)]
    closures = {(c.date, c.shift): c for c in ShiftClosure.objects.filter(date__in=recent_days)}
    shift_rows = []
    for d in recent_days:
        for s in Shift.values:
            start, _ = shift_bounds(d, s)
            if start > now:
                continue
            closure = closures.get((d, s))
            shift_rows.append({"day": d, "shift": s, "label": Shift(s).label, "closure": closure,
                               "missing": len((closure.summary or {}).get("missing", [])) if closure else None,
                               "current": (d, s) == (day, shift)})

    ctx.update({
        "doses_total": len(doses), "doses_done": sum(1 for d in doses if d.done),
        "checklist_total": status["total"], "checklist_done": status["done"],
        "protocols": _protocols_with_actions(),
        "sos_pending": TherapyAdministration.objects.filter(
            is_sos=True, validation_status=TherapyAdministration.Validation.PENDING).select_related("guest", "therapy__drug"),
        "serious_events": ClinicalEvent.objects.filter(occurred_at__gte=now - datetime.timedelta(hours=48)).filter(
            Q(severity__in=["high", "critical"]) | Q(is_emergency=True)).select_related("guest")[:8],
        "restraints": Restraint.objects.filter(ended_at__isnull=True).select_related("guest"),
        "shift_rows": shift_rows,
        "pai_due": PAI.objects.filter(status=PAI.Status.ACTIVE,
                                      review_due__lte=today + datetime.timedelta(days=config.pai_review_warning_days))
        .select_related("guest").order_by("review_due"),
        "without_pai": [g for g in in_care if g.pk not in with_pai],
        "stock_low": [r for r in stock if r["low"]][:6],
        "stock_expiring": sum(len(r["expiring"]) + len(r["expired"]) for r in stock),
        "appointments": Appointment.objects.filter(
            status=Appointment.Status.SCHEDULED, scheduled_at__date__in=[today, today + datetime.timedelta(days=1)]
        ).select_related("guest", "companion"),
        "documents_expiring": Document.objects.filter(
            expires_on__isnull=False, expires_on__lte=today + datetime.timedelta(days=30)
        ).exclude(guest__status="archived").select_related("guest").order_by("expires_on")[:6],
        "therapy_alerts": Therapy.objects.exclude(conflict_acknowledged="").filter(
            updated_at__gte=now - datetime.timedelta(days=14)).select_related("guest", "drug")[:6],
    })
    return ctx


def doctor(request):
    from fasas.clinical.models import ClinicalEvent, ParameterReading, Restraint, Therapy, TherapyAdministration
    from fasas.documents.views import documents_to_sign
    from fasas.guests.services import guests_in_care
    from fasas.signatures.models import SigningCredential

    now = timezone.now()
    today = timezone.localdate()
    readings = ParameterReading.objects.filter(occurred_at__gte=now - datetime.timedelta(hours=48)).select_related(
        "guest", "parameter_type")
    guests = guests_in_care().annotate(
        therapy_count=Count("therapies", filter=Q(therapies__status="active", therapies__is_sos=False), distinct=True),
        sos_count=Count("therapies", filter=Q(therapies__status="active", therapies__is_sos=True), distinct=True),
        allergy_count=Count("allergies", distinct=True),
    )
    return _guest_counts() | {
        "sos_pending": TherapyAdministration.objects.filter(
            is_sos=True, validation_status=TherapyAdministration.Validation.PENDING
        ).select_related("guest", "therapy__drug", "created_by"),
        "out_of_range": [r for r in readings if r.out_of_range][:12],
        "events": ClinicalEvent.objects.filter(occurred_at__gte=now - datetime.timedelta(days=7)).filter(
            Q(severity__in=["medium", "high", "critical"]) | Q(event_type__in=["seizure", "fall", "emergency"])
        ).select_related("guest")[:8],
        "restraints": Restraint.objects.filter(ended_at__isnull=True).select_related("guest", "authorized_by"),
        "therapies_ending": Therapy.objects.filter(
            status=Therapy.Status.ACTIVE, end_date__gte=today, end_date__lte=today + datetime.timedelta(days=7)
        ).select_related("guest", "drug").order_by("end_date"),
        "therapy_alerts": Therapy.objects.exclude(conflict_acknowledged="").exclude(status=Therapy.Status.ENDED).filter(
            updated_at__gte=now - datetime.timedelta(days=30)).select_related("guest", "drug")[:6],
        "to_sign": documents_to_sign(limit=8),
        "credential": SigningCredential.objects.filter(user=request.user).first(),
        "guests": guests,
    }


def admin(request):
    from fasas.accounts.models import AccessLog, Role, User
    from fasas.audit.models import AuditLog
    from fasas.audit.services import verify_chain
    from fasas.backups.models import BackupRecord
    from fasas.notifications.models import NotificationSetting
    from fasas.protocols.models import Protocol

    now = timezone.now()
    since = now - datetime.timedelta(hours=24)
    config = SystemConfig.get()
    users = User.objects.filter(is_active=True)
    role_counts = dict(users.order_by().values_list("role").annotate(n=Count("pk")))
    last_ok = BackupRecord.objects.filter(status=BackupRecord.Status.OK).first()
    audit_count = AuditLog.objects.count()
    chain = verify_chain() if audit_count <= 20000 else None

    warnings = []
    if settings.DEBUG:
        warnings.append("Il sistema è in modalità di prova (DEBUG attivo): non usarlo con dati reali.")
    if not settings.FASAS_ALLOWED_NETWORKS:
        warnings.append("Nessuna restrizione di rete: il sistema è raggiungibile da qualsiasi indirizzo (FASAS_ALLOWED_NETWORKS).")
    if last_ok is None or last_ok.created_at < now - datetime.timedelta(hours=26):
        warnings.append("Nessun backup riuscito nelle ultime 26 ore.")
    if chain is not None and not chain[0]:
        warnings.append(f"Catena di integrità dell'audit log interrotta alla voce #{chain[2]}.")

    config_changes = AuditLog.objects.filter(
        Q(action__in=[AuditLog.Action.CONFIG, AuditLog.Action.PERMISSION, AuditLog.Action.BACKUP])
        | Q(content_type__model__in=["user", "userpermissionoverride", "systemconfig", "notificationsetting", "protocol"])
    ).order_by("-id")[:10]

    return {
        "roles": [(label, role_counts.get(code, 0)) for code, label in Role.choices],
        "users_total": users.count(),
        "users_inactive": User.objects.filter(is_active=False).count(),
        "users_custom": User.objects.filter(permission_overrides__isnull=False).distinct().count(),
        "failed_24h": AccessLog.objects.filter(timestamp__gte=since, event__in=["failed", "locked"]).count(),
        "logins_24h": AccessLog.objects.filter(timestamp__gte=since, event="login").count(),
        "recent_failures": AccessLog.objects.filter(event__in=["failed", "locked"])[:8],
        "backups": BackupRecord.objects.select_related("created_by")[:5],
        "last_ok_backup": last_ok,
        "audit_count": audit_count,
        "chain": chain,
        "config": config,
        "protocols_active": Protocol.objects.filter(active=True).count(),
        "protocols_unvalidated": Protocol.objects.filter(active=True, validated_by="").count(),
        "notifications_disabled": NotificationSetting.objects.filter(enabled=False).count(),
        "config_changes": config_changes,
        "warnings": warnings,
    }


def administrative(request):
    from fasas.billing.views import billing_overview

    return billing_overview()


BUILDERS = {"operator": operator, "coordinator": coordinator, "doctor": doctor, "admin": admin,
            "administrative": administrative}
