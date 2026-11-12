import datetime

from django.utils import timezone

from fasas.core.locking import creation_decision

from .models import Assessment, ScaleSetting
from .scales import SCALES


class AssessmentError(Exception):
    pass


def settings_by_code():
    """Impostazioni di tutte le scale (create alla prima lettura con i valori predefiniti)."""
    existing = {s.code: s for s in ScaleSetting.objects.all()}
    missing = [ScaleSetting(code=code, enabled=scale.enabled_by_default, interval_days=scale.interval_days)
               for code, scale in SCALES.items() if code not in existing]
    if missing:
        ScaleSetting.objects.bulk_create(missing, ignore_conflicts=True)
        existing = {s.code: s for s in ScaleSetting.objects.all()}
    return existing


def enabled_scales():
    configured = settings_by_code()
    return [(SCALES[code], configured[code]) for code in SCALES if configured[code].enabled]


def score(scale, answers):
    """Somma dei punteggi scelti; ogni voce deve avere un punteggio previsto dalla scala."""
    clean, total = {}, 0
    for item in scale.items:
        try:
            points = int(answers.get(item.key))
        except (TypeError, ValueError):
            raise AssessmentError(f"Manca il punteggio di «{item.label}».") from None
        if points not in dict(item.options):
            raise AssessmentError(f"Punteggio non previsto per «{item.label}».")
        clean[item.key] = points
        total += points
    band = scale.band_for(total)
    return clean, total, band


def create_assessment(guest, scale_code, answers, user, occurred_at=None, notes=""):
    scale = SCALES.get(scale_code)
    if scale is None:
        raise AssessmentError("Scala non prevista.")
    setting = settings_by_code()[scale_code]
    if not setting.enabled:
        raise AssessmentError("Questa scala non è in uso nella struttura (Impostazioni › Scale di valutazione).")
    occurred_at = occurred_at or timezone.now()
    if occurred_at > timezone.now() + datetime.timedelta(minutes=10):
        raise AssessmentError("La data della valutazione è nel futuro.")
    decision = creation_decision(guest, occurred_at, user)
    if not decision.allowed:
        raise AssessmentError(decision.message)
    clean, total, band = score(scale, answers)
    day = timezone.localtime(occurred_at).date()
    next_due = day + datetime.timedelta(days=setting.interval_days) if setting.interval_days else None
    return Assessment.objects.create(
        guest=guest, scale=scale_code, answers=clean, total=total, band=band.label, band_level=band.level,
        next_due=next_due, notes=notes, occurred_at=occurred_at,
    )


def latest_by_scale(guest):
    latest = {}
    for assessment in Assessment.objects.filter(guest=guest).order_by("-occurred_at"):
        latest.setdefault(assessment.scale, assessment)
    return latest


def due_list(today=None, guests=None):
    """Valutazioni da ripetere: scale in uso con una frequenza, mai fatte o scadute (entro 7 giorni = in scadenza)."""
    from fasas.guests.models import Guest

    today = today or timezone.localdate()
    scheduled = [(scale, setting) for scale, setting in enabled_scales() if setting.interval_days]
    if not scheduled:
        return []
    guests = list(guests if guests is not None else Guest.objects.filter(status=Guest.Status.ACTIVE))
    latest = {}
    for assessment in Assessment.objects.filter(guest__in=guests).order_by("-occurred_at"):
        latest.setdefault((assessment.guest_id, assessment.scale), assessment)
    rows = []
    for guest in guests:
        for scale, _setting in scheduled:
            last = latest.get((guest.pk, scale.code))
            due = last.next_due if last else guest.admission_date
            if last is None or due <= today + datetime.timedelta(days=7):
                rows.append({"guest": guest, "scale": scale, "last": last, "due": due,
                             "overdue": last is None or due < today})
    return sorted(rows, key=lambda r: (r["due"], r["guest"].last_name))


def due_reminders(today=None):
    """Job: avvisa il coordinatore delle valutazioni scadute o mai fatte (una volta per scadenza)."""
    from django.urls import reverse

    from fasas.notifications.services import notify

    today = today or timezone.localdate()
    sent = 0
    for row in due_list(today):
        if not row["overdue"]:
            continue
        what = "mai eseguita" if row["last"] is None else f"scaduta il {row['due']:%d/%m/%Y}"
        notify("assessment_due", f"Valutazione da ripetere: {row['scale'].name} – {row['guest']}",
               f"{row['scale'].name} {what}.", link=reverse("assessments:guest", args=[row["guest"].pk]),
               guest=row["guest"], dedup_key=f"assessment-{row['guest'].pk}-{row['scale'].code}-{row['due']}")
        sent += 1
    return {"overdue": sent}
