"""
Indicatori del pilota: pochi numeri da confrontare con il cartaceo.

- Dosi programmate, registrate, mancanti e registrate in ritardo: dal riepilogo salvato alla chiusura di ogni turno
  (daily.services.dose_summary), quindi fedeli a com'era il turno anche se le terapie cambiano dopo.
- Durata del giro farmaci: per ogni orario programmato di un giorno, il tempo tra la prima e l'ultima registrazione
  (con almeno due dosi registrate).
- Completamento della checklist di turno e segnalazioni ricevute.
"""
import datetime
import statistics

from django.db.models import Count, Max, Min
from django.utils import timezone

from fasas.clinical.models import TherapyAdministration
from fasas.core.shifts import SHIFT_ORDER
from fasas.daily.models import ShiftClosure

from .models import Feedback

MAX_DAYS = 62


def _median(values):
    return round(statistics.median(values)) if values else None


def _percent(part, total):
    return round(100 * part / total) if total else None


def pilot_metrics(start, end):
    days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
    rows = {day: {"day": day, "closed": 0, "doses_total": 0, "doses_documented": 0, "doses_missing": 0,
                  "doses_late": 0, "checklist_total": 0, "checklist_done": 0, "rounds": [], "feedback": 0}
            for day in days}

    for closure in ShiftClosure.objects.filter(date__range=(start, end), reopened_at__isnull=True):
        row, summary = rows[closure.date], closure.summary or {}
        if "doses_total" not in summary:  # turni chiusi prima di questa versione: niente conteggio delle dosi
            continue
        row["closed"] += 1
        for key in ("doses_total", "doses_documented", "doses_missing", "doses_late", "checklist_total",
                    "checklist_done"):
            row[key] += summary.get(key, 0)

    slots = {}
    for group in (TherapyAdministration.objects
                  .filter(scheduled_date__range=(start, end), scheduled_time__isnull=False, is_sos=False,
                          voided_at__isnull=True)
                  .values("scheduled_date", "scheduled_time")
                  .annotate(first=Min("created_at"), last=Max("created_at"), n=Count("id"))):
        if group["n"] < 2:
            continue
        minutes = (group["last"] - group["first"]).total_seconds() / 60
        rows[group["scheduled_date"]]["rounds"].append(minutes)
        slots.setdefault(group["scheduled_time"], []).append(minutes)

    for item in (Feedback.objects.filter(created_at__date__range=(start, end))
                 .values("created_at__date").annotate(n=Count("id"))):
        rows[item["created_at__date"]]["feedback"] = item["n"]

    table = []
    for day in days:
        row = rows[day]
        row["round_median"] = _median(row.pop("rounds"))
        row["documented_pct"] = _percent(row["doses_documented"], row["doses_total"])
        row["checklist_pct"] = _percent(row["checklist_done"], row["checklist_total"])
        table.append(row)

    totals = {key: sum(r[key] for r in table) for key in (
        "closed", "doses_total", "doses_documented", "doses_missing", "doses_late", "checklist_total",
        "checklist_done", "feedback")}
    all_rounds = [m for minutes in slots.values() for m in minutes]
    totals.update({
        "documented_pct": _percent(totals["doses_documented"], totals["doses_total"]),
        "late_pct": _percent(totals["doses_late"], totals["doses_documented"]),
        "checklist_pct": _percent(totals["checklist_done"], totals["checklist_total"]),
        "round_median": _median(all_rounds), "rounds": len(all_rounds),
        "expected_closures": len(days) * len(SHIFT_ORDER),
    })
    by_slot = [{"time": t, "rounds": len(m), "median": _median(m), "max": round(max(m))}
               for t, m in sorted(slots.items())]
    by_kind = [{"label": label, "n": Feedback.objects.filter(created_at__date__range=(start, end), kind=kind).count()}
               for kind, label in Feedback.Kind.choices]
    return {"rows": table, "totals": totals, "slots": by_slot, "feedback_by_kind": by_kind,
            "open_feedback": Feedback.objects.filter(status__in=Feedback.OPEN).count()}


def default_period(today=None):
    today = today or timezone.localdate()
    return today - datetime.timedelta(days=13), today
