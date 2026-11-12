import datetime
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from fasas.accounts.models import Role, User
from fasas.billing.services import month_days, month_start
from fasas.core.shifts import shift_bounds

from .models import (
    ABSENCE_CODES,
    SHIFT_CODES,
    WORK_CODES,
    Code,
    LeaveRequest,
    RequestStatus,
    RotaEntry,
    RotaMonth,
    RotaSettings,
    ShiftChange,
    StaffProfile,
)

ROTA_ROLES = (Role.OPERATOR, Role.COORDINATOR)


class RotaError(Exception):
    pass


def staff():
    """Personale nel calendario: operatori e coordinatori attivi (con profilo turni creato al bisogno)."""
    users = list(User.objects.filter(is_active=True, role__in=ROTA_ROLES).order_by("last_name", "first_name"))
    existing = {p.user_id: p for p in StaffProfile.objects.filter(user__in=users)}
    for user in users:
        if user.pk not in existing:
            existing[user.pk] = StaffProfile.objects.create(user=user, can_lead=user.role == Role.COORDINATOR)
    people = [(u, existing[u.pk]) for u in users if existing[u.pk].in_rota]
    people.sort(key=lambda pair: (pair[1].order, pair[0].last_name, pair[0].first_name))
    return people


def shift_hours(code, day=None):
    day = day or timezone.localdate()
    if code not in SHIFT_CODES:
        return Decimal("0")
    start, end = shift_bounds(day, code)
    return Decimal((end - start).total_seconds() / 3600).quantize(Decimal("0.1"))


def _entries(first, last, users=None):
    qs = RotaEntry.objects.filter(date__gte=first, date__lte=last)
    if users is not None:
        qs = qs.filter(user__in=users)
    return {(e.user_id, e.date): e for e in qs}


def rest_warnings(people, entries, days, rules):
    """Riposo minimo tra turni consecutivi e giorni lavorativi consecutivi (D.Lgs. 66/2003)."""
    warnings = []
    min_rest = datetime.timedelta(hours=rules.min_rest_hours)
    for user, profile in people:
        streak = 0
        for index, day in enumerate(days):
            entry = entries.get((user.pk, day))
            code = entry.code if entry else ""
            if code == Code.NIGHT and profile.no_nights:
                warnings.append({"day": day, "user": user, "level": "warn", "text": f"{user}: esonerato dalle notti"})
            streak = streak + 1 if code in WORK_CODES else 0
            if streak == rules.max_consecutive_days + 1:
                warnings.append({"day": day, "user": user, "level": "warn",
                                 "text": f"{user}: più di {rules.max_consecutive_days} giorni di lavoro consecutivi"})
            if code in SHIFT_CODES and index + 1 < len(days):
                nxt = entries.get((user.pk, days[index + 1]))
                if nxt and nxt.code in SHIFT_CODES:
                    rest = shift_bounds(days[index + 1], nxt.code)[0] - shift_bounds(day, code)[1]
                    if rest < min_rest:
                        hours = max(0, int(rest.total_seconds() // 3600))
                        warnings.append({"day": days[index + 1], "user": user, "level": "danger",
                                         "text": f"{user}: {Code(code).label.lower()} seguito da "
                                                 f"{Code(nxt.code).label.lower()} – riposo di {hours} ore"})
    return warnings


def coverage(people, entries, days, rules):
    rows = {code: [] for code in SHIFT_CODES}
    gaps = []
    for day in days:
        for code in SHIFT_CODES:
            count = sum(1 for user, _ in people if (e := entries.get((user.pk, day))) and e.code == code)
            minimum = rules.minimum(code)
            rows[code].append({"day": day, "count": count, "min": minimum, "ok": count >= minimum})
            if count < minimum:
                gaps.append({"day": day, "code": code, "count": count, "min": minimum})
    return rows, gaps


def month_grid(first):
    rules = RotaSettings.get()
    days = month_days(first)
    people = staff()
    entries = _entries(days[0], days[-1], [u for u, _ in people])
    weeks = Decimal(len(days)) / 7
    rows = []
    for user, profile in people:
        cells, hours, absences, counts = [], Decimal("0"), 0, defaultdict(int)
        for day in days:
            entry = entries.get((user.pk, day))
            code = entry.code if entry else ""
            cells.append({"day": day, "code": code, "lead": bool(entry and entry.is_lead)})
            counts[code] += 1
            if code in SHIFT_CODES:
                hours += shift_hours(code, day)
            elif code == Code.TRAINING:
                hours += rules.training_hours
            elif code in ABSENCE_CODES:
                absences += 1
        expected = (profile.weekly_hours * (Decimal(len(days) - absences)) / 7).quantize(Decimal("0.1"))
        rows.append({"user": user, "profile": profile, "cells": cells, "hours": hours, "expected": expected,
                     "delta": hours - expected, "holidays": counts[Code.HOLIDAY], "nights": counts[Code.NIGHT]})
    cover_rows, gaps = coverage(people, entries, days, rules)
    return {
        "days": days, "rows": rows, "coverage": cover_rows, "gaps": gaps, "rules": rules, "weeks": weeks,
        "warnings": rest_warnings(people, entries, days, rules), "people": people,
        "month": RotaMonth.objects.filter(month=first).first(),
    }


def _notify_change(user, day, old, new):
    from fasas.notifications.services import notify

    if day < timezone.localdate():
        return
    month = RotaMonth.objects.filter(month=month_start(day)).first()
    if not month or not month.is_published:
        return
    label = lambda c: Code(c).label.lower() if c else "nessun turno"  # noqa: E731
    notify("rota_changed", f"Turno del {day:%d/%m} cambiato", f"Il tuo turno del {day:%d/%m/%Y} è passato da "
           f"{label(old)} a {label(new)}.", link=reverse("staffing:my"), users=[user], dedup_key="")


@transaction.atomic
def set_entry(user, day, code, notify=True, is_lead=None):
    if code and code not in Code.values:
        raise RotaError(f"Codice non valido: {code}")
    entry = RotaEntry.objects.filter(user=user, date=day).first()
    old = entry.code if entry else ""
    if not code:
        if entry:
            entry.delete()
    elif entry:
        if entry.code != code or (is_lead is not None and entry.is_lead != is_lead):
            entry.code = code
            if is_lead is not None:
                entry.is_lead = is_lead
            entry.save()
    else:
        RotaEntry.objects.create(user=user, date=day, code=code, is_lead=bool(is_lead))
    if notify and old != code:
        _notify_change(user, day, old, code)
    return old


@transaction.atomic
def apply_changes(changes, editor):
    """Modifiche dal calendario: [{"user": id, "day": "AAAA-MM-GG", "code": "M"}]."""
    allowed = {u.pk: u for u, _ in staff()}
    applied = 0
    for change in changes:
        user = allowed.get(int(change.get("user", 0) or 0))
        if user is None:
            raise RotaError("Operatore non presente nel calendario.")
        try:
            day = datetime.date.fromisoformat(change["day"])
        except (KeyError, TypeError, ValueError):
            raise RotaError("Giorno non valido.") from None
        set_entry(user, day, change.get("code") or "", is_lead=change.get("lead"))
        applied += 1
    return applied


@transaction.atomic
def repeat_cycle(first, weeks=4):
    """Riempie i giorni vuoti del mese ripetendo lo schema di N settimane prima (turnazioni cicliche)."""
    days = month_days(first)
    people = [u for u, _ in staff()]
    offset = datetime.timedelta(days=7 * weeks)
    entries = _entries(days[0] - offset, days[-1], people)
    created = 0
    for day in days:  # in ordine di giorno: i turni appena creati alimentano le settimane successive
        for user in people:
            source = entries.get((user.pk, day - offset))
            if (user.pk, day) in entries or source is None or source.code in ABSENCE_CODES:
                continue
            entries[(user.pk, day)] = RotaEntry.objects.create(user=user, date=day, code=source.code,
                                                                is_lead=source.is_lead)
            created += 1
    return created


@transaction.atomic
def publish(first, editor, notes=""):
    from fasas.notifications.services import notify

    month, _ = RotaMonth.objects.get_or_create(month=first)
    first_publication = not month.is_published
    month.status = RotaMonth.Status.PUBLISHED
    month.published_at = timezone.now()
    month.published_by = editor
    if notes:
        month.notes = notes
    month.save()
    people = [u for u, _ in staff()]
    title = f"Turni di {first:%m/%Y} {'pubblicati' if first_publication else 'aggiornati'}"
    notify("rota_published", title, month.notes or "Consulta i tuoi turni in FASAS.", link=reverse("staffing:my"),
           users=people)
    return month


# --- Ferie, permessi, cambi turno -------------------------------------------------------------

def _days(start, end):
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def coverage_impact(user, days, new_code):
    """Turni che scenderebbero sotto il minimo se user lasciasse il suo turno in quei giorni."""
    rules = RotaSettings.get()
    issues = []
    for day in days:
        entry = RotaEntry.objects.filter(user=user, date=day).first()
        if entry and entry.code in SHIFT_CODES and new_code != entry.code:
            count = RotaEntry.objects.filter(date=day, code=entry.code).count() - 1
            if count < rules.minimum(entry.code):
                issues.append(f"{day:%d/%m} {Code(entry.code).label.lower()}: resterebbero {count} su "
                              f"{rules.minimum(entry.code)}")
    return issues


def request_leave(user, kind, start, end, note=""):
    from fasas.notifications.services import notify

    if end < start:
        raise RotaError("La data di fine precede l'inizio.")
    if (end - start).days > 60:
        raise RotaError("Massimo 60 giorni per richiesta.")
    overlapping = LeaveRequest.objects.filter(user=user, status__in=[RequestStatus.PENDING, RequestStatus.APPROVED],
                                              start__lte=end, end__gte=start)
    if overlapping.exists():
        raise RotaError("C'è già una richiesta per questi giorni.")
    leave = LeaveRequest.objects.create(user=user, kind=kind, start=start, end=end, note=note)
    notify("rota_request", f"Richiesta di {leave.get_kind_display().lower()}: {user}",
           f"{leave.get_kind_display()} dal {start:%d/%m} al {end:%d/%m} ({leave.days} giorni). {note}".strip(),
           link=reverse("staffing:requests"))
    return leave


@transaction.atomic
def decide_leave(leave, editor, approve, note=""):
    from fasas.notifications.services import notify

    if leave.status != RequestStatus.PENDING:
        raise RotaError("La richiesta è già stata gestita.")
    leave.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
    leave.decided_by, leave.decided_at, leave.decision_note = editor, timezone.now(), note[:255]
    leave.save()
    if approve:
        for day in _days(leave.start, leave.end):
            set_entry(leave.user, day, leave.kind, notify=False)
    notify("rota_answer", f"{leave.get_kind_display()} {'approvate' if approve else 'non approvate'}",
           f"{leave.get_kind_display()} dal {leave.start:%d/%m} al {leave.end:%d/%m}: "
           f"{'approvata' if approve else 'respinta'}{'. ' + note if note else '.'}",
           link=reverse("staffing:my"), users=[leave.user])
    return leave


def _code(user, day):
    entry = RotaEntry.objects.filter(user=user, date=day).first()
    return entry.code if entry else ""


def propose_change(requester, kind, day, colleague, note=""):
    from fasas.notifications.services import notify

    if colleague == requester:
        raise RotaError("Scegliere un collega diverso.")
    if day < timezone.localdate():
        raise RotaError("Non si possono cambiare turni passati.")
    mine, theirs = _code(requester, day), _code(colleague, day)
    if mine not in SHIFT_CODES:
        raise RotaError("Quel giorno non hai un turno da cambiare.")
    if kind == ShiftChange.Kind.SWAP and (theirs not in SHIFT_CODES or theirs == mine):
        raise RotaError("Per un cambio il collega deve avere un turno diverso nello stesso giorno.")
    if kind == ShiftChange.Kind.COVER and theirs in SHIFT_CODES:
        raise RotaError("Il collega è già in turno quel giorno: proporre un cambio turno.")
    if kind == ShiftChange.Kind.COVER and theirs in ABSENCE_CODES:
        raise RotaError("Il collega è assente quel giorno.")
    change = ShiftChange.objects.create(kind=kind, date=day, requester=requester, colleague=colleague,
                                        requester_code=mine, colleague_code=theirs or Code.REST, note=note,
                                        created_by=requester)
    what = (f"scambiare il tuo turno ({Code(change.colleague_code).label.lower()}) con il suo "
            f"({Code(mine).label.lower()})" if kind == ShiftChange.Kind.SWAP
            else f"coprire il suo turno di {Code(mine).label.lower()}")
    notify("rota_answer", f"{requester} ti chiede un cambio turno", f"Il {day:%d/%m}: {what}. {note}".strip(),
           link=reverse("staffing:my"), users=[colleague])
    return change


def respond_change(change, colleague, accept):
    from fasas.notifications.services import notify

    if change.colleague_id != colleague.pk or change.status != RequestStatus.PENDING:
        raise RotaError("Richiesta non disponibile.")
    change.status = RequestStatus.ACCEPTED if accept else RequestStatus.REJECTED
    change.save()
    if accept:
        notify("rota_request", f"Cambio turno da approvare: {change.requester} ↔ {change.colleague}",
               f"{change.get_kind_display()} del {change.date:%d/%m}, accettato dal collega.",
               link=reverse("staffing:requests"))
    notify("rota_answer", f"{colleague} ha {'accettato' if accept else 'rifiutato'} il cambio del {change.date:%d/%m}",
           "In attesa dell'approvazione del coordinatore." if accept else "", link=reverse("staffing:my"),
           users=[change.requester])
    return change


@transaction.atomic
def decide_change(change, editor, approve, note=""):
    from fasas.notifications.services import notify

    if change.status not in (RequestStatus.ACCEPTED, RequestStatus.PENDING):
        raise RotaError("La richiesta è già stata gestita.")
    if approve and change.status != RequestStatus.ACCEPTED:
        raise RotaError("Il collega non ha ancora accettato.")
    if approve:
        mine, theirs = _code(change.requester, change.date), _code(change.colleague, change.date)
        if mine != change.requester_code or (theirs or Code.REST) != change.colleague_code:
            raise RotaError("Nel frattempo i turni di quel giorno sono cambiati: chiedere di ripresentare la richiesta.")
        if change.kind == ShiftChange.Kind.SWAP:
            set_entry(change.requester, change.date, change.colleague_code, notify=False)
            set_entry(change.colleague, change.date, change.requester_code, notify=False)
        else:
            set_entry(change.colleague, change.date, change.requester_code, notify=False)
            set_entry(change.requester, change.date, change.requester_new_code, notify=False)
    change.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
    change.decided_by, change.decided_at, change.decision_note = editor, timezone.now(), note[:255]
    change.save()
    notify("rota_answer", f"{change.get_kind_display()} del {change.date:%d/%m} "
           f"{'approvato' if approve else 'non approvato'}", note, link=reverse("staffing:my"),
           users=[change.requester, change.colleague])
    return change


def upcoming(user, days=7):
    """Prossimi turni pubblicati di un utente (per il cruscotto)."""
    today = timezone.localdate()
    published = set(RotaMonth.objects.filter(status=RotaMonth.Status.PUBLISHED).values_list("month", flat=True))
    entries = RotaEntry.objects.filter(user=user, date__gte=today, date__lte=today + datetime.timedelta(days=days))
    return [e for e in entries.order_by("date") if month_start(e.date) in published]


def today_coverage():
    """Copertura pianificata di oggi e domani per il coordinatore."""
    rules = RotaSettings.get()
    today = timezone.localdate()
    rows = []
    for day in (today, today + datetime.timedelta(days=1)):
        for code in SHIFT_CODES:
            names = [str(e.user) for e in RotaEntry.objects.filter(date=day, code=code).select_related("user")]
            rows.append({"day": day, "code": code, "label": Code(code).label, "names": names,
                         "ok": len(names) >= rules.minimum(code), "min": rules.minimum(code)})
    return rows

