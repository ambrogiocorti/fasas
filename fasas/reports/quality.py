"""
Indicatori di qualità mese per mese (ultimi 12 mesi): cadute, eventi gravi, nuove lesioni da pressione insorte in
struttura, contenzioni, farmaci SOS, ricoveri. Le frequenze sono per 1000 giornate di presenza, come negli
indicatori di esito delle strutture residenziali, così si confrontano mesi con un numero diverso di ospiti.
Conta solo le registrazioni valide (non annullate). Dati aggregati, senza nomi.
"""
import csv
import datetime
import io
from dataclasses import dataclass, field

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone


@dataclass
class Indicator:
    key: str
    label: str
    help: str
    rate: bool = True  # per 1000 giornate di presenza; altrimenti percentuale degli ospiti
    values: list = field(default_factory=list)
    rates: list = field(default_factory=list)


INDICATORS = [
    ("falls", "Cadute", "Eventi «caduta» registrati nel mese"),
    ("falls_injury", "Cadute con conseguenze", "Cadute di gravità alta o critica, o con conseguenze descritte"),
    ("serious", "Eventi gravi o critici", "Tutti gli eventi sanitari di gravità alta o critica"),
    ("pressure", "Nuove lesioni da pressione", "Lesioni da pressione insorte in struttura (non quelle già presenti all'ingresso)"),
    ("restraints", "Contenzioni avviate", "Nuove contenzioni registrate nel mese"),
    ("sos", "Farmaci SOS somministrati", "Somministrazioni al bisogno effettivamente date"),
    ("hospital", "Ricoveri ospedalieri", "Movimenti «ricovero ospedaliero» registrati nel mese"),
]


def month_starts(count=12, end=None):
    end = end or timezone.localdate()
    first = end.replace(day=1)
    months = []
    for _ in range(count):
        months.append(first)
        first = (first - datetime.timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def month_end(first):
    return (first + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)


def guest_days(months, today):
    """Giornate in carico per mese (dall'ingresso alla dimissione, ricoveri compresi) e ospiti con almeno un giorno."""
    from fasas.guests.models import Guest

    days = {m: 0 for m in months}
    present = {m: set() for m in months}
    start, stop = months[0], min(month_end(months[-1]), today)
    for guest in Guest.objects.filter(admission_date__lte=stop).filter(
            Q(discharge_date__isnull=True) | Q(discharge_date__gte=start)).only("pk", "admission_date", "discharge_date"):
        last = min(guest.discharge_date or stop, stop)
        for m in months:
            lo, hi = max(m, guest.admission_date), min(month_end(m), last)
            if hi >= lo:
                days[m] += (hi - lo).days + 1
                present[m].add(guest.pk)
    return days, {m: len(present[m]) for m in months}


def _by_month(queryset, field_name, start, stop):
    rows = (queryset.filter(**{f"{field_name}__range": (start, stop)})
            .annotate(month=TruncMonth(field_name)).values("month").annotate(n=Count("id")))
    result = {}
    for row in rows:
        month = row["month"]
        month = month.date() if isinstance(month, datetime.datetime) else month
        result[month] = row["n"]
    return result


def monthly(count=12, today=None):
    from fasas.clinical.models import ClinicalEvent, Restraint, TherapyAdministration
    from fasas.guests.models import AdmissionEvent
    from fasas.wounds.models import Wound

    today = today or timezone.localdate()
    months = month_starts(count, today)
    start, stop = months[0], month_end(months[-1])
    serious = Q(severity__in=[ClinicalEvent.Severity.HIGH, ClinicalEvent.Severity.CRITICAL])
    falls = ClinicalEvent.objects.filter(event_type=ClinicalEvent.EventType.FALL)
    counts = {
        "falls": _by_month(falls, "shift_date", start, stop),
        "falls_injury": _by_month(falls.filter(serious | ~Q(injuries="")), "shift_date", start, stop),
        "serious": _by_month(ClinicalEvent.objects.filter(serious), "shift_date", start, stop),
        "pressure": _by_month(Wound.objects.filter(kind=Wound.Kind.PRESSURE, origin=Wound.Origin.IN_HOUSE),
                              "shift_date", start, stop),
        "restraints": _by_month(Restraint.objects.all(), "shift_date", start, stop),
        "sos": _by_month(TherapyAdministration.objects.filter(therapy__is_sos=True,
                                                              status=TherapyAdministration.Status.GIVEN),
                         "shift_date", start, stop),
        "hospital": _by_month(AdmissionEvent.objects.filter(kind=AdmissionEvent.Kind.HOSPITALIZATION),
                              "date", start, stop),
    }
    days, guests = guest_days(months, today)
    indicators = []
    for key, label, help_text in INDICATORS:
        indicator = Indicator(key, label, help_text)
        for m in months:
            value = counts[key].get(m, 0)
            indicator.values.append(value)
            indicator.rates.append(round(value * 1000 / days[m], 2) if days[m] else None)
        indicators.append(indicator)
    # ospiti con almeno un giorno di contenzione nel mese (percentuale degli ospiti in carico)
    restraint_guests = Indicator("restraint_guests", "Ospiti con contenzione",
                                 "Ospiti con una contenzione in corso per almeno un giorno del mese", rate=False)
    for m in months:
        lo = timezone.make_aware(datetime.datetime.combine(m, datetime.time.min))
        hi = timezone.make_aware(datetime.datetime.combine(month_end(m) + datetime.timedelta(days=1), datetime.time.min))
        value = (Restraint.objects.filter(occurred_at__lt=hi).filter(Q(ended_at__isnull=True) | Q(ended_at__gte=lo))
                 .values("guest").distinct().count())
        restraint_guests.values.append(value)
        restraint_guests.rates.append(round(value * 100 / guests[m], 1) if guests[m] else None)
    indicators.insert(5, restraint_guests)
    for indicator in indicators:
        top = max(indicator.values) or 1
        indicator.bars = [{"month": m, "value": v, "rate": r, "height": round(v * 100 / top)}
                          for m, v, r in zip(months, indicator.values, indicator.rates, strict=True)]
        indicator.total = sum(indicator.values)
        # confronto sull'ultimo mese CONCLUSO (quello in corso è parziale) con la media dei mesi precedenti
        previous = [r for r in indicator.rates[:-2] if r is not None]
        indicator.average = round(sum(previous) / len(previous), 2) if previous else None
        indicator.last = indicator.rates[-2] if len(indicator.rates) > 1 else None
        indicator.trend = (None if indicator.average is None or indicator.last is None
                           else "up" if indicator.last > indicator.average * 1.2
                           else "down" if indicator.last < indicator.average * 0.8 else "flat")
    return {"months": months, "guest_days": [days[m] for m in months], "guests": [guests[m] for m in months],
            "indicators": indicators, "today": today}


def export_csv(data):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Indicatore", "Unità"] + [f"{m:%m/%Y}" for m in data["months"]])
    writer.writerow(["Giornate di presenza", "giorni"] + data["guest_days"])
    writer.writerow(["Ospiti in carico", "ospiti"] + data["guests"])
    for indicator in data["indicators"]:
        writer.writerow([indicator.label, "numero"] + indicator.values)
        unit = "per 1000 giornate" if indicator.rate else "% degli ospiti"
        writer.writerow([indicator.label, unit] + [("" if r is None else str(r).replace(".", ",")) for r in indicator.rates])
    return "﻿" + output.getvalue()
