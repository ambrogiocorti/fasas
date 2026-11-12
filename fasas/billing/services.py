import calendar
import datetime
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from fasas.audit.models import AuditLog, lock_audit_chain
from fasas.audit.services import log_event
from fasas.guests.models import AdmissionEvent, Guest

from .models import (
    ABSENCES,
    AttendanceCorrection,
    AttendanceMonth,
    AttendanceMonthRow,
    AttendanceStatus,
    BillingSettings,
    FeePayment,
    FeeStatement,
    GuestFeeLine,
    StatementSequence,
)

S = AttendanceStatus
CENT = Decimal("0.01")


class BillingError(Exception):
    pass


# --- Mesi -------------------------------------------------------------------------------------

def month_start(day=None):
    day = day or timezone.localdate()
    return day.replace(day=1)


def month_days(first):
    return [first.replace(day=d) for d in range(1, calendar.monthrange(first.year, first.month)[1] + 1)]


def month_end(first):
    return month_days(first)[-1]


def parse_month(text):
    """«2026-10» → 1 ottobre 2026; altrimenti il mese corrente."""
    try:
        year, month = (int(x) for x in str(text).split("-")[:2])
        return datetime.date(year, month, 1)
    except (TypeError, ValueError):
        return month_start()


def shift_month(first, delta):
    month = first.month - 1 + delta
    return datetime.date(first.year + month // 12, month % 12 + 1, 1)


# --- Presenze dai movimenti -------------------------------------------------------------------

def _events_by_guest(guests):
    events = {}
    for event in AdmissionEvent.objects.filter(guest__in=guests).order_by("date", "created_at", "pk"):
        events.setdefault(event.guest_id, []).append(event)
    return events


def guest_days(guest, days, events, corrections, rules):
    """Presenza giorno per giorno secondo i movimenti dell'ospite e le regole di conteggio."""
    K = AdmissionEvent.Kind
    timeline = list(events)
    if not any(e.kind == K.ADMISSION for e in timeline):
        timeline.insert(0, AdmissionEvent(kind=K.ADMISSION, date=guest.admission_date))
    timeline.sort(key=lambda e: e.date)
    result = OrderedDict()
    for day in days:
        upto = [e for e in timeline if e.date <= day]
        if not upto:
            status = S.NOT_IN_CARE
        else:
            last = upto[-1]
            same_day = last.date == day
            if last.kind == K.ADMISSION:
                status = S.PRESENT if (not same_day or rules.count_admission_day) else S.NOT_IN_CARE
            elif last.kind in (K.HOSPITALIZATION, K.ABSENCE):
                away = S.HOSPITAL if last.kind == K.HOSPITALIZATION else S.FAMILY
                status = S.PRESENT if (same_day and rules.departure_day_present) else away
            elif last.kind == K.RETURN:
                if same_day and not rules.return_day_present:
                    before = [e for e in upto[:-1] if e.kind in (K.HOSPITALIZATION, K.ABSENCE)]
                    status = (S.HOSPITAL if before and before[-1].kind == K.HOSPITALIZATION else S.FAMILY) \
                        if before else S.PRESENT
                else:
                    status = S.PRESENT
            elif last.kind == K.DISCHARGE:
                status = S.PRESENT if (same_day and rules.count_discharge_day) else S.NOT_IN_CARE
            else:
                status = S.PRESENT
        if day in corrections:
            status = corrections[day].status
        result[day.day] = str(status)
    return result


def guests_for_month(first):
    last = month_end(first)
    return Guest.objects.filter(admission_date__lte=last).filter(
        Q(discharge_date__isnull=True) | Q(discharge_date__gte=first)).order_by("last_name", "first_name")


def counts(days):
    values = list(days.values())
    return {"present": values.count(S.PRESENT), "hospital": values.count(S.HOSPITAL),
            "family": values.count(S.FAMILY), "absent": values.count(S.ABSENT)}


def compute_month(first):
    """[(ospite, {giorno: codice}, conteggi)] calcolati dai movimenti (mese aperto)."""
    rules = BillingSettings.get()
    days = month_days(first)
    guests = list(guests_for_month(first))
    events = _events_by_guest(guests)
    corrections = {}
    for c in AttendanceCorrection.objects.filter(guest__in=guests, date__gte=days[0], date__lte=days[-1]):
        corrections.setdefault(c.guest_id, {})[c.date] = c
    rows = []
    for guest in guests:
        values = guest_days(guest, days, events.get(guest.pk, []), corrections.get(guest.pk, {}), rules)
        if all(v == S.NOT_IN_CARE for v in values.values()):
            continue
        rows.append((guest, values, counts(values), set(d.day for d in corrections.get(guest.pk, {}))))
    return rows


def attendance(first):
    """Presenze del mese: dalla «fotografia» se il mese è chiuso, altrimenti calcolate."""
    month = AttendanceMonth.objects.filter(month=first).first()
    if month and month.is_closed:
        rows = []
        for row in month.rows.select_related("guest").order_by("guest__last_name", "guest__first_name"):
            days = OrderedDict((int(k), v) for k, v in sorted(row.days.items(), key=lambda kv: int(kv[0])))
            rows.append((row.guest, days, counts(days), set()))
        return month, rows
    return month, compute_month(first)


# --- Correzioni, chiusura e riapertura --------------------------------------------------------

def save_correction(guest, day, status, reason, user):
    month = AttendanceMonth.objects.filter(month=month_start(day)).first()
    if month and month.is_closed:
        raise BillingError("Il mese è chiuso: riaprirlo (con motivazione) per correggere le presenze.")
    if not reason.strip():
        raise BillingError("Indicare il motivo della correzione.")
    correction, _ = AttendanceCorrection.objects.update_or_create(
        guest=guest, date=day, defaults={"status": status, "reason": reason.strip()[:255]})
    return correction


@transaction.atomic
def close_month(first, user, notes=""):
    lock_audit_chain()
    if month_end(first) >= timezone.localdate():
        raise BillingError("Si può chiudere un mese solo dopo il suo ultimo giorno.")
    month, _ = AttendanceMonth.objects.select_for_update().get_or_create(month=first)
    if month.is_closed:
        raise BillingError("Il mese è già chiuso.")
    rows = compute_month(first)
    month.rows.all().delete()
    AttendanceMonthRow.objects.bulk_create([
        AttendanceMonthRow(month=month, guest=guest, days={str(k): v for k, v in days.items()}, **c)
        for guest, days, c, _ in rows
    ])
    month.status = AttendanceMonth.Status.CLOSED
    month.closed_at = timezone.now()
    month.closed_by = user
    if notes:
        month.notes = notes
    month.save()
    totals = {k: sum(r[2][k] for r in rows) for k in ("present", "hospital", "family", "absent")}
    log_event(AuditLog.Action.CLOSE, month, user=user, changes={"presenze": [None, totals]},
              reason=f"Chiusura presenze {first:%m/%Y}")
    return month


@transaction.atomic
def reopen_month(month, user, reason):
    lock_audit_chain()
    if not reason.strip():
        raise BillingError("Indicare il motivo della riapertura.")
    if month.statements.filter(status__in=[FeeStatement.Status.ISSUED, FeeStatement.Status.PAID]).exists():
        raise BillingError("Ci sono prospetti già emessi per questo mese: annullarli prima di riaprire le presenze.")
    month.statements.filter(status=FeeStatement.Status.DRAFT).delete()
    month.status = AttendanceMonth.Status.OPEN
    month.reopen_reason = reason.strip()[:255]
    month.save()
    log_event(AuditLog.Action.REOPEN, month, user=user, reason=reason)
    return month


# --- Rette ---------------------------------------------------------------------------------------

def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def statement_lines(fee_lines, days, first):
    """Righe del prospetto per le voci di uno stesso pagante: giorni per tipo di presenza × tariffa × %."""
    lines = []
    for fee in fee_lines:
        by_status = OrderedDict((s, 0) for s in (S.PRESENT, S.HOSPITAL, S.FAMILY, S.ABSENT))
        over_cap = 0
        absences = 0
        for day_number, status in days.items():
            day = first.replace(day=int(day_number))
            if status not in by_status or not fee.valid_on(day):
                continue
            if status in ABSENCES:
                absences += 1
                if fee.max_absence_days is not None and absences > fee.max_absence_days:
                    over_cap += 1
                    continue
            by_status[status] += 1
        for status, count in by_status.items():
            if not count:
                continue
            percent = fee.percent_for(status)
            amount = _money(count * fee.daily_rate * Decimal(percent) / 100)
            lines.append({"description": fee.description, "status": str(status), "status_label": S(status).label,
                          "days": count, "rate": str(fee.daily_rate), "percent": percent, "amount": str(amount)})
        if over_cap:
            lines.append({"description": fee.description, "status": "X",
                          "status_label": f"Assenze oltre il limite di {fee.max_absence_days} giorni",
                          "days": over_cap, "rate": str(fee.daily_rate), "percent": 0, "amount": "0.00"})
    return lines


@transaction.atomic
def generate_statements(month, user):
    """Bozze dei prospetti del mese chiuso: una per ospite e intestatario. Le bozze precedenti si rigenerano."""
    if not month.is_closed:
        raise BillingError("Chiudere prima le presenze del mese.")
    first, last = month.month, month_end(month.month)
    month.statements.filter(status=FeeStatement.Status.DRAFT).delete()
    emitted = set(month.statements.exclude(status=FeeStatement.Status.CANCELLED)
                  .values_list("guest_id", "payer_name"))
    created, skipped, missing = [], 0, []
    for row in month.rows.select_related("guest"):
        fees = list(GuestFeeLine.objects.filter(guest=row.guest, valid_from__lte=last)
                    .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=first)))
        if not fees:
            missing.append(row.guest)
            continue
        groups = OrderedDict()
        for fee in fees:
            groups.setdefault((fee.payer, fee.payer_name), []).append(fee)
        for (payer, payer_name), group in groups.items():
            if (row.guest_id, payer_name) in emitted:
                skipped += 1
                continue
            lines = statement_lines(group, row.days, first)
            if not lines:
                continue
            ref = group[0]
            created.append(FeeStatement.objects.create(
                month=month, guest=row.guest, payer=payer, payer_name=payer_name, payer_tax_code=ref.payer_tax_code,
                payer_address=ref.payer_address, payer_email=ref.payer_email, lines=lines,
                total=sum((Decimal(line["amount"]) for line in lines), Decimal("0")), created_by=user,
            ))
    return created, skipped, missing


@transaction.atomic
def issue_statement(statement, user, issue_date=None):
    lock_audit_chain()
    statement = FeeStatement.objects.select_for_update().get(pk=statement.pk)
    if statement.status != FeeStatement.Status.DRAFT:
        raise BillingError("Il prospetto è già stato emesso.")
    issue_date = issue_date or timezone.localdate()
    sequence, _ = StatementSequence.objects.select_for_update().get_or_create(year=issue_date.year)
    sequence.last += 1
    sequence.save()
    statement.year, statement.sequence = issue_date.year, sequence.last
    statement.number = f"{issue_date.year}/{sequence.last:04d}"
    statement.issue_date = issue_date
    statement.due_date = issue_date + datetime.timedelta(days=BillingSettings.get().payment_terms_days)
    statement.status = FeeStatement.Status.PAID if statement.total == 0 else FeeStatement.Status.ISSUED
    statement.save()
    return statement


@transaction.atomic
def cancel_statement(statement, user, reason):
    if not reason.strip():
        raise BillingError("Indicare il motivo dell'annullamento.")
    if statement.payments.exists():
        raise BillingError("Il prospetto ha incassi registrati: non può essere annullato.")
    if statement.status == FeeStatement.Status.DRAFT:
        statement.delete()
        return None
    statement.status = FeeStatement.Status.CANCELLED
    statement.cancel_reason = reason.strip()[:255]
    statement.save()
    return statement


@transaction.atomic
def register_payment(statement, amount, date, method, reference, user):
    if statement.status not in (FeeStatement.Status.ISSUED, FeeStatement.Status.PAID):
        raise BillingError("Si registrano incassi solo su prospetti emessi.")
    payment = FeePayment.objects.create(statement=statement, amount=amount, date=date, method=method,
                                        reference=reference, created_by=user)
    if statement.balance <= 0 and statement.status != FeeStatement.Status.PAID:
        statement.status = FeeStatement.Status.PAID
        statement.save(update_fields=["status"])
    return payment
