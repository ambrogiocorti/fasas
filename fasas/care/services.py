"""Attività a orario: elenco del turno, spunta con le regole delle registrazioni, avviso dei ritardi."""
import datetime
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from fasas.core.locking import creation_decision
from fasas.core.shifts import resolve_shift, scheduled_moment, shift_bounds, time_in_shift

from .models import CareTask, CareTaskCheck

# Si può spuntare un'attività fino a un'ora prima dell'orario previsto (non oltre: sarebbe un'altra volta)
EARLY_TOLERANCE = datetime.timedelta(minutes=60)
FUTURE_TOLERANCE = datetime.timedelta(minutes=10)


class CareError(Exception):
    def __init__(self, message, *, conflict=False):
        super().__init__(message)
        self.message = message
        self.conflict = conflict


@dataclass
class Slot:
    task: CareTask
    day: datetime.date
    time: datetime.time
    moment: datetime.datetime
    check: CareTaskCheck | None

    @property
    def guest(self):
        return self.task.guest

    @property
    def done(self):
        return self.check is not None

    def late(self, now=None):
        now = now or timezone.now()
        return self.check is None and now > self.moment + datetime.timedelta(minutes=self.task.late_minutes)

    @property
    def key(self):
        return f"{self.task.pk}-{self.day:%Y%m%d}-{self.time:%H%M}"


def active_tasks(guests=None):
    tasks = CareTask.objects.filter(active=True).exclude(guest__status="archived").select_related("guest")
    if guests is not None:
        tasks = tasks.filter(guest__in=guests)
    return tasks


def shift_slots(day, shift, guests=None):
    """Tutte le attività previste in un turno, con l'eventuale spunta già fatta."""
    tasks = list(active_tasks(guests))
    start, end = shift_bounds(day, shift)
    days = sorted({start.date(), (end - datetime.timedelta(seconds=1)).date()})
    checks = {(c.task_id, c.scheduled_date, c.scheduled_time): c for c in CareTaskCheck.objects.filter(
        task__in=tasks, scheduled_date__in=days).select_related("created_by")}
    slots = []
    for task in tasks:
        for t in task.parsed_times():
            if not time_in_shift(t, shift):
                continue
            moment = scheduled_moment(day, shift, t)
            actual_day = timezone.localtime(moment).date()
            if not task.is_active_on(actual_day):
                continue
            slots.append(Slot(task, actual_day, t, moment, checks.get((task.pk, actual_day, t))))
    slots.sort(key=lambda s: (s.moment, s.guest.last_name, s.task.kind))
    return slots


def late_slots(now=None, guests=None):
    """Attività in ritardo nel turno in corso e in quello precedente (non ancora spuntate)."""
    from fasas.core.shifts import previous_shift

    now = now or timezone.now()
    day, shift = resolve_shift(now)
    prev_day, prev_shift = previous_shift(day, shift)
    slots = shift_slots(prev_day, prev_shift, guests) + shift_slots(day, shift, guests)
    return [s for s in slots if s.late(now)]


def find_slot(task, scheduled_date, scheduled_time):
    """L'orario indicato deve essere uno di quelli del piano, in un giorno in cui il piano vale."""
    if scheduled_time not in task.parsed_times():
        raise CareError(f"Le {scheduled_time:%H:%M} non sono tra gli orari previsti per «{task.name}».")
    if not task.is_active_on(scheduled_date):
        raise CareError(f"Il {scheduled_date:%d/%m/%Y} l'attività «{task.name}» non è prevista.")
    shift = resolve_shift(timezone.make_aware(datetime.datetime.combine(scheduled_date, scheduled_time)))
    return timezone.make_aware(datetime.datetime.combine(scheduled_date, scheduled_time)), shift


@transaction.atomic
def register_check(task, user, scheduled_date, scheduled_time, status=CareTaskCheck.Status.DONE, notes="",
                   occurred_at=None, now=None):
    now = now or timezone.now()
    occurred_at = occurred_at or now
    task = CareTask.objects.select_for_update().select_related("guest").get(pk=task.pk)
    if status not in CareTaskCheck.Status.values:
        raise CareError("Esito non previsto.")
    if task.guest.is_archived:
        raise CareError("La cartella dell'ospite è archiviata: non si registrano attività.")
    if not task.active:
        raise CareError("Il piano di questa attività è terminato.")
    moment, _ = find_slot(task, scheduled_date, scheduled_time)
    if occurred_at > now + FUTURE_TOLERANCE:
        raise CareError("L'ora indicata è nel futuro.")
    if moment - occurred_at > EARLY_TOLERANCE:
        raise CareError(f"Troppo presto: l'attività è prevista alle {scheduled_time:%H:%M}.")
    if status != CareTaskCheck.Status.DONE and not notes.strip():
        raise CareError("Indicare il motivo (es. ospite che dorme, rifiuto, assente).")
    for when in (occurred_at, moment):
        decision = creation_decision(task.guest, when, user)
        if not decision.allowed:
            raise CareError(decision.message)
    existing = CareTaskCheck.objects.filter(task=task, scheduled_date=scheduled_date,
                                            scheduled_time=scheduled_time).select_related("created_by").first()
    if existing:
        raise CareError(f"Già registrata da {existing.created_by or 'un collega'} alle "
                        f"{timezone.localtime(existing.occurred_at):%H:%M}.", conflict=True)
    try:
        with transaction.atomic():
            return CareTaskCheck.objects.create(task=task, guest=task.guest, scheduled_date=scheduled_date,
                                                scheduled_time=scheduled_time, status=status, notes=notes.strip(),
                                                occurred_at=occurred_at)
    except IntegrityError:
        raise CareError("Già registrata da un collega in questo momento.", conflict=True) from None


@transaction.atomic
def end_task(task, user, reason, end_date=None):
    if not reason.strip():
        raise CareError("Indicare il motivo della fine (es. lesione guarita, indicazione del medico).")
    task.active = False
    task.end_date = end_date or timezone.localdate()
    task.end_reason = reason.strip()[:255]
    task.updated_by = user
    task.save(update_fields=["active", "end_date", "end_reason", "updated_by", "updated_at"])
    return task


def late_reminders(now=None):
    """Job (ogni 15 minuti): un avviso al coordinatore per ogni attività in ritardo (una volta per orario)."""
    from fasas.notifications.services import notify

    sent = 0
    for slot in late_slots(now):
        notify("care_late", f"Attività in ritardo: {slot.guest}",
               f"{slot.task.name} prevista alle {slot.time:%H:%M} non ancora registrata.",
               link=reverse("care:due"), guest=slot.guest, dedup_key=f"care-{slot.key}")
        sent += 1
    return {"late": sent}
