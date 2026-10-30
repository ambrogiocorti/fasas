import datetime
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from fasas.core.shifts import resolve_shift, scheduled_moment, shift_bounds, time_in_shift
from fasas.pharmacy.models import DrugInteraction

from .models import ClinicalEvent, Therapy, TherapyAdministration

# --- Controllo duplicati, interazioni e allergie --------------------------------------------

@dataclass
class TherapyWarning:
    level: str  # warning | danger
    kind: str
    message: str

    def __str__(self):
        return self.message


def _norm(text):
    return " ".join((text or "").lower().replace("-", " ").split())


def _ingredients(drug):
    """Un farmaco può avere più principi attivi separati da '+', ',' o '/'."""
    raw = drug.active_ingredient or ""
    for sep in ["+", "/", ";"]:
        raw = raw.replace(sep, ",")
    return {_norm(part) for part in raw.split(",") if part.strip()}


THERAPY_CHECK_NOTICE = ("Promemoria calcolati confrontando i dati registrati dalla struttura (terapie, allergie, "
                        "tabella delle interazioni validata dal medico): non sostituiscono la valutazione del medico.")


def check_therapy_conflicts(guest, drug, exclude_therapy=None):
    """
    Promemoria su una nuova terapia, secondo gli interruttori in Configurazione (docs/DISPOSITIVO_MEDICO.md):
    duplicati, allergie registrate e interazioni della tabella validata dal medico della struttura.
    """
    from fasas.core.models import SystemConfig

    config = SystemConfig.get()
    warnings = []
    active = Therapy.objects.filter(guest=guest).exclude(status=Therapy.Status.ENDED).select_related("drug")
    if exclude_therapy is not None and exclude_therapy.pk:
        active = active.exclude(pk=exclude_therapy.pk)
    new_ingredients = _ingredients(drug)
    atc = (drug.atc_code or "").upper()

    for therapy in (active if config.therapy_check_duplicates else []):
        other = therapy.drug
        if other.pk == drug.pk:
            warnings.append(TherapyWarning("danger", "duplicate",
                f"Farmaco duplicato: {other} è già in terapia ({therapy.dose_display}{', SOS' if therapy.is_sos else ''})."))
            continue
        shared = new_ingredients & _ingredients(other)
        if shared:
            warnings.append(TherapyWarning("danger", "duplicate",
                f"Stesso principio attivo ({', '.join(sorted(shared))}) già presente con {other}."))
        elif atc and other.atc_code and len(atc) >= 5 and atc[:5] == other.atc_code.upper()[:5]:
            warnings.append(TherapyWarning("warning", "duplicate",
                f"Possibile duplicazione terapeutica: {other} appartiene allo stesso gruppo ATC ({atc[:5]})."))

    other_ingredients = {}
    for therapy in active:
        for ingredient in _ingredients(therapy.drug):
            other_ingredients.setdefault(ingredient, therapy.drug)
    if config.therapy_check_interactions and new_ingredients and other_ingredients:
        pairs = DrugInteraction.objects.filter(validated_at__isnull=False)  # solo regole validate dal medico
        for interaction in pairs:
            a, b = _norm(interaction.ingredient_a), _norm(interaction.ingredient_b)
            for mine, theirs in ((a, b), (b, a)):
                if mine in new_ingredients and theirs in other_ingredients:
                    level = "danger" if interaction.severity == DrugInteraction.Severity.MAJOR else "warning"
                    warnings.append(TherapyWarning(level, "interaction",
                        f"Interazione {interaction.get_severity_display().lower()} con {other_ingredients[theirs]}: "
                        f"{interaction.description}"))

    for allergy in (guest.allergies.filter(category="drug") if config.therapy_check_allergies else []):
        substance = _norm(allergy.substance)
        if substance and (substance in new_ingredients or substance in _norm(drug.name)
                          or any(substance in ing or ing in substance for ing in new_ingredients)):
            warnings.append(TherapyWarning("danger", "allergy",
                f"ALLERGIA registrata: {allergy.substance} ({allergy.get_severity_display()}). "
                f"{allergy.reaction}".strip()))
    return warnings


def notify_conflicts(therapy, warnings, user):
    from fasas.notifications.services import notify

    if not warnings:
        return
    notify(
        "therapy_conflict",
        f"Avvisi su nuova terapia: {therapy.guest}",
        f"{therapy} inserita da {user} nonostante: " + " | ".join(w.message for w in warnings),
        link=therapy.get_absolute_url(), guest=therapy.guest,
        level="critical" if any(w.kind == "allergy" for w in warnings) else "warning",
    )


# --- Giro farmaci ---------------------------------------------------------------------------

@dataclass
class ScheduledDose:
    therapy: Therapy
    day: datetime.date
    time: datetime.time
    moment: datetime.datetime
    administration: TherapyAdministration | None

    @property
    def guest(self):
        return self.therapy.guest

    @property
    def done(self):
        return self.administration is not None

    @property
    def overdue(self):
        return not self.done and timezone.now() > self.moment + datetime.timedelta(minutes=60)


def scheduled_doses(day, shift, guests=None):
    """Tutte le dosi programmate in un turno con lo stato di somministrazione."""
    therapies = Therapy.objects.filter(status=Therapy.Status.ACTIVE, is_sos=False).select_related("drug", "guest")
    therapies = therapies.exclude(guest__status="archived")
    if guests is not None:
        therapies = therapies.filter(guest__in=guests)
    start, end = shift_bounds(day, shift)
    days = sorted({start.date(), (end - datetime.timedelta(seconds=1)).date()})

    given = {}
    for adm in TherapyAdministration.objects.filter(
        therapy__in=therapies, scheduled_date__in=days, scheduled_time__isnull=False
    ):
        given[(adm.therapy_id, adm.scheduled_date, adm.scheduled_time)] = adm

    doses = []
    for therapy in therapies:
        for t in therapy.parsed_times():
            if not time_in_shift(t, shift):
                continue
            moment = scheduled_moment(day, shift, t)
            actual_day = timezone.localtime(moment).date()
            if not therapy.is_active_on(actual_day):
                continue
            doses.append(ScheduledDose(therapy, actual_day, t, moment, given.get((therapy.pk, actual_day, t))))
    doses.sort(key=lambda d: (d.moment, d.guest.last_name, d.therapy.drug.name))
    return doses


@transaction.atomic
def register_administration(therapy, user, status=TherapyAdministration.Status.GIVEN, scheduled_date=None,
                            scheduled_time=None, occurred_at=None, notes="", dose_given="", sos_reason=""):
    from fasas.pharmacy.services import unload_for_administration

    occurred_at = occurred_at or timezone.now()
    administration = TherapyAdministration(
        guest=therapy.guest, therapy=therapy, scheduled_date=scheduled_date, scheduled_time=scheduled_time,
        status=status, occurred_at=occurred_at, notes=notes, dose_given=dose_given or therapy.dose_display,
        is_sos=therapy.is_sos, sos_reason=sos_reason,
    )
    if therapy.is_sos:
        needs_validation = therapy.sos_requires_validation and not user.has_perm("clinical.validate_sos")
        administration.validation_status = (
            TherapyAdministration.Validation.PENDING if needs_validation else TherapyAdministration.Validation.NOT_REQUIRED
        )
        if therapy.sos_requires_validation and not needs_validation:
            administration.validation_status = TherapyAdministration.Validation.VALIDATED
            administration.validated_by = user
            administration.validated_at = timezone.now()
    administration.save()

    if status == TherapyAdministration.Status.GIVEN:
        unload_for_administration(administration, therapy.stock_units_per_dose, user)

    if therapy.is_sos:
        _after_sos(administration)
    return administration


def sos_limits_warnings(therapy, at=None):
    """Avvisi prima di una somministrazione SOS: superamento massimo giornaliero o intervallo minimo."""
    at = at or timezone.now()
    warnings = []
    recent = TherapyAdministration.objects.filter(
        therapy=therapy, status=TherapyAdministration.Status.GIVEN, occurred_at__gte=at - datetime.timedelta(hours=24)
    ).order_by("-occurred_at")
    if therapy.sos_max_daily and recent.count() >= therapy.sos_max_daily:
        warnings.append(f"Raggiunto il massimo di {therapy.sos_max_daily} somministrazioni nelle 24 ore.")
    last = recent.first()
    if therapy.sos_min_interval_hours and last:
        elapsed = at - last.occurred_at
        if elapsed < datetime.timedelta(hours=therapy.sos_min_interval_hours):
            minutes = int(elapsed.total_seconds() // 60)
            warnings.append(
                f"Ultima somministrazione {minutes} minuti fa: intervallo minimo {therapy.sos_min_interval_hours} ore."
            )
    return warnings


def _after_sos(administration):
    from fasas.notifications.services import notify
    from fasas.protocols.engine import on_sos_administration

    if administration.validation_status == TherapyAdministration.Validation.PENDING:
        notify(
            "sos_validation",
            f"SOS da validare: {administration.guest}",
            f"{administration.therapy} somministrato. Motivo: {administration.sos_reason}",
            link=reverse("clinical:sos_pending"), guest=administration.guest, level="warning",
        )
    on_sos_administration(administration)


def validate_sos(administration, user, approve, notes=""):
    administration.validation_status = (
        TherapyAdministration.Validation.VALIDATED if approve else TherapyAdministration.Validation.REJECTED
    )
    administration.validated_by = user
    administration.validated_at = timezone.now()
    administration.validation_notes = notes
    administration.save(update_fields=["validation_status", "validated_by", "validated_at", "validation_notes",
                                       "updated_at", "updated_by"])
    return administration


def void_administration(administration, user, reason):
    from fasas.pharmacy.services import reverse_administration

    reverse_administration(administration, user)
    administration.void(user, reason)


# --- Eventi ---------------------------------------------------------------------------------

def after_event_saved(event, created):
    """Notifiche per eventi gravi, emergenze e tag clinici con escalation; aggancio ai protocolli."""
    from fasas.notifications.services import notify
    from fasas.protocols.engine import on_clinical_event

    if not created:
        return
    escalating_tags = [tag for tag in event.guest.tags.all() if event.event_type in (tag.escalate_event_types or [])]
    critical = event.is_emergency or event.severity in (ClinicalEvent.Severity.HIGH, ClinicalEvent.Severity.CRITICAL)
    if critical or escalating_tags:
        extra = f" Tag: {', '.join(t.name for t in escalating_tags)}." if escalating_tags else ""
        notify(
            "emergency_event" if event.is_emergency else "critical_event",
            f"{'EMERGENZA' if event.is_emergency else 'Evento'}: {event.get_event_type_display()} – {event.guest}",
            f"{event.description[:300]}{extra}",
            link=reverse("clinical:event_detail", args=[event.pk]), guest=event.guest, level="critical",
        )
    on_clinical_event(event)


def recent_parameters(guest, days=7):
    since = timezone.now() - datetime.timedelta(days=days)
    return guest.parameterreadings.filter(occurred_at__gte=since).select_related("parameter_type")


def latest_parameters(guest):
    """Ultimo valore per ciascun tipo di parametro."""
    latest = {}
    for reading in guest.parameterreadings.select_related("parameter_type").order_by("-occurred_at")[:200]:
        latest.setdefault(reading.parameter_type_id, reading)
    return sorted(latest.values(), key=lambda r: r.parameter_type.order)


def chart_series(guest, parameter_type, days=90):
    since = timezone.now() - datetime.timedelta(days=days)
    readings = guest.parameterreadings.filter(parameter_type=parameter_type, occurred_at__gte=since).order_by("occurred_at")
    return {
        "name": parameter_type.name,
        "unit": parameter_type.unit,
        "min": float(parameter_type.min_normal) if parameter_type.min_normal is not None else None,
        "max": float(parameter_type.max_normal) if parameter_type.max_normal is not None else None,
        "points": [
            {"t": timezone.localtime(r.occurred_at).isoformat(), "v": float(r.value),
             "v2": float(r.value_2) if r.value_2 is not None else None}
            for r in readings
        ],
    }


def active_restraints():
    return Q(ended_at__isnull=True) | Q(ended_at__gt=timezone.now())


def current_shift():
    return resolve_shift()
