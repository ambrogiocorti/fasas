import datetime

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from fasas.audit.context import audit_context
from fasas.audit.models import AuditLog, lock_audit_chain
from fasas.audit.services import log_event
from fasas.core.models import SystemConfig
from fasas.core.shifts import SHIFT_ORDER, Shift, previous_shift, resolve_shift, shift_bounds

from .models import ChecklistCheck, ChecklistItem, ChecklistTemplate, DailyRecord, EvacuationRecord, ShiftClosure


class ShiftClosedError(Exception):
    pass


# --- Blocco giornata ------------------------------------------------------------------------

def is_shift_closed(day, shift):
    return ShiftClosure.objects.filter(date=day, shift=shift, reopened_at__isnull=True).exists()


def is_day_closed(day):
    return ShiftClosure.objects.filter(date=day, reopened_at__isnull=True).count() == len(SHIFT_ORDER)


@transaction.atomic
def close_shift(day, shift, user=None, automatic=False, handover_notes=""):
    """Chiude il turno: da questo momento i dati del turno non sono più modificabili."""
    lock_audit_chain()
    existing = ShiftClosure.objects.select_for_update().filter(date=day, shift=shift).first()
    if existing and existing.is_closed:
        return existing
    status = checklist_status(day, shift)
    summary = {
        "checklist_total": status["total"],
        "checklist_done": status["done"],
        "missing": [f"{m['guest']}: {m['item']}" for m in status["missing"]][:200],
    }
    if existing:  # turno riaperto in via straordinaria che viene richiuso
        existing.reopened_at = None
        existing.closed_at = timezone.now()
        existing.closed_by = user
        existing.automatic = automatic
        existing.summary = summary
        existing.handover_notes = handover_notes or existing.handover_notes
        existing.save()
        closure = existing
    else:
        closure = ShiftClosure.objects.create(
            date=day, shift=shift, closed_by=user, automatic=automatic, summary=summary, handover_notes=handover_notes
        )
    log_event(AuditLog.Action.CLOSE, closure, user=user, changes={"mancanti": [None, len(status["missing"])]})
    if status["missing"]:
        from fasas.notifications.services import notify

        notify(
            "checklist_missing",
            f"Turno {Shift(shift).label} del {day:%d/%m/%Y} chiuso con attività mancanti",
            f"{len(status['missing'])} voci di checklist non completate.",
            link=reverse("daily:closure_detail", args=[closure.pk]), level="warning",
            dedup_key=f"checklist-missing-{day}-{shift}",
        )
    return closure


@transaction.atomic
def reopen_shift(closure, user, reason):
    config = SystemConfig.get()
    if not config.allow_admin_reopen:
        raise ShiftClosedError("La riapertura dei turni chiusi è disabilitata nella configurazione.")
    if not user.has_perm("daily.reopen_shift"):
        raise ShiftClosedError("Non hai il permesso di riaprire un turno.")
    with audit_context(reason=reason):
        closure.reopened_at = timezone.now()
        closure.reopened_by = user
        closure.reopen_reason = reason
        closure.save()
    log_event(AuditLog.Action.REOPEN, closure, user=user, reason=reason)
    return closure


def auto_close_shifts(now=None):
    """Job: chiude i turni terminati da più dei minuti di tolleranza configurati."""
    config = SystemConfig.get()
    if not config.auto_close_shifts:
        return {"closed": 0}
    now = now or timezone.now()
    grace = datetime.timedelta(minutes=config.auto_close_grace_minutes)
    closed = 0
    day, shift = resolve_shift(now, config)
    # controlla gli ultimi 9 turni (3 giorni)
    for _ in range(9):
        day, shift = previous_shift(day, shift)
        _, end = shift_bounds(day, shift, config)
        if end + grace <= now and not ShiftClosure.objects.filter(date=day, shift=shift).exists():
            try:
                close_shift(day, shift, automatic=True)
                closed += 1
            except IntegrityError:
                pass
    return {"closed": closed}


# --- Evacuazioni ------------------------------------------------------------------------------

def last_evacuation(guest):
    return EvacuationRecord.objects.filter(guest=guest, outcome=True).order_by("-occurred_at").first()


def days_since_last_evacuation(guest, today=None):
    """Giorni dall'ultima evacuazione; senza registrazioni conta dall'inizio del monitoraggio."""
    today = today or timezone.localdate()
    last = last_evacuation(guest)
    if last is not None:
        reference = timezone.localtime(last.occurred_at).date()
    else:
        reference = max(guest.admission_date, timezone.localtime(guest.created_at).date())
    return (today - reference).days, last


def evacuation_overview(guests, today=None):
    rows = []
    for guest in guests:
        days, last = days_since_last_evacuation(guest, today)
        rows.append({"guest": guest, "days": days, "last": last})
    return sorted(rows, key=lambda r: -r["days"])


# --- Checklist di turno -----------------------------------------------------------------------

def _guest_has_tags(guest, item):
    required = {t.pk for t in item.required_tags.all()}
    if not required:
        return True
    return bool(required & {t.pk for t in guest.tags.all()})


def checklist_status(day, shift, guests=None):
    """
    Stato di ogni voce di checklist per ogni ospite nel turno:
    ✔ completato, ⚠ mancante, — non applicabile.
    """
    from fasas.clinical.models import ParameterReading
    from fasas.clinical.services import scheduled_doses
    from fasas.guests.services import guests_in_care

    config = SystemConfig.get()
    guests = list(guests if guests is not None else guests_in_care().filter(status="active"))
    items = list(
        ChecklistItem.objects.filter(template__shift=shift, template__active=True)
        .select_related("template", "parameter_type").prefetch_related("required_tags")
        .order_by("template__name", "order", "pk")
    )
    start, end = shift_bounds(day, shift, config)

    checks = {(c.item_id, c.guest_id): c for c in ChecklistCheck.objects.filter(date=day, shift=shift)}
    records = list(DailyRecord.objects.filter(shift_date=day, shift=shift).values("guest_id", "category", "meal"))
    params = list(ParameterReading.objects.filter(shift_date=day, shift=shift).values("guest_id", "parameter_type_id"))
    evacuations = set(EvacuationRecord.objects.filter(shift_date=day).values_list("guest_id", flat=True))
    doses = scheduled_doses(day, shift, guests)
    doses_by_guest = {}
    for dose in doses:
        doses_by_guest.setdefault(dose.guest.pk, []).append(dose)

    def auto_state(item, guest):
        kind = item.check_type
        if kind == ChecklistItem.CheckType.THERAPY:
            mine = doses_by_guest.get(guest.pk, [])
            if not mine:
                return "na"
            return "ok" if all(d.done for d in mine) else "missing"
        if kind == ChecklistItem.CheckType.PARAMETERS:
            ok = any(p["guest_id"] == guest.pk and (item.parameter_type_id is None or
                                                     p["parameter_type_id"] == item.parameter_type_id) for p in params)
            return "ok" if ok else "missing"
        if kind == ChecklistItem.CheckType.MEAL:
            ok = any(r["guest_id"] == guest.pk and r["category"] == DailyRecord.Category.MEAL and
                     (not item.meal or r["meal"] == item.meal) for r in records)
            return "ok" if ok else "missing"
        if kind == ChecklistItem.CheckType.HYGIENE:
            ok = any(r["guest_id"] == guest.pk and r["category"] == DailyRecord.Category.HYGIENE for r in records)
            return "ok" if ok else "missing"
        if kind == ChecklistItem.CheckType.EVACUATION:
            if config.evacuation_mode != SystemConfig.EvacuationMode.DAILY:
                return "na"
            return "ok" if guest.pk in evacuations else "missing"
        return "missing"

    rows = []
    total = done = 0
    missing = []
    for item in items:
        targets = guests if item.per_guest else [None]
        cells = []
        for guest in targets:
            if guest is not None and not _guest_has_tags(guest, item):
                cells.append({"guest": guest, "state": "na", "check": None})
                continue
            check = checks.get((item.pk, guest.pk if guest else None))
            if check is not None:
                state = "na" if check.not_applicable else "ok"
            elif item.check_type == ChecklistItem.CheckType.MANUAL:
                state = "missing"
            else:
                state = auto_state(item, guest) if guest else "missing"
            if state != "na":
                total += 1
                if state == "ok":
                    done += 1
                else:
                    missing.append({"guest": guest or "Turno", "item": item.label})
            cells.append({"guest": guest, "state": state, "check": check})
        rows.append({"item": item, "cells": cells})
    return {"rows": rows, "guests": guests, "total": total, "done": done, "missing": missing,
            "start": start, "end": end}


def mark_check(day, shift, item, user, guest=None, not_applicable=False, notes=""):
    if is_shift_closed(day, shift):
        raise ShiftClosedError("Il turno è chiuso.")
    check, created = ChecklistCheck.objects.get_or_create(
        date=day, shift=shift, item=item, guest=guest,
        defaults={"done_by": user, "not_applicable": not_applicable, "notes": notes},
    )
    if not created:
        check.not_applicable = not_applicable
        check.notes = notes
        check.done_by = user
        check.done_at = timezone.now()
        check.save()
    return check


def unmark_check(day, shift, item, guest=None):
    if is_shift_closed(day, shift):
        raise ShiftClosedError("Il turno è chiuso.")
    for check in ChecklistCheck.objects.filter(date=day, shift=shift, item=item, guest=guest):
        check.delete()


def default_templates_exist():
    return ChecklistTemplate.objects.exists()
