"""
Pacchetto dati per lavorare senza rete: il minimo indispensabile per il turno in corso e il successivo
(dosi da somministrare, farmaci SOS, allergie, avvisi, contatti di emergenza, protocolli aperti).

Il pacchetto viene cifrato nel browser (AES-GCM, chiave protetta dalla password dell'utente) prima di
essere salvato sul dispositivo: vedi static/js/offline.js.
"""
import datetime

from django.utils import timezone

from fasas.clinical.models import ClinicalEvent, ParameterType, Therapy, TherapyAdministration
from fasas.clinical.services import scheduled_doses
from fasas.core.models import SystemConfig
from fasas.core.shifts import Shift, resolve_shift, shift_bounds
from fasas.guests.services import guests_in_care

PACK_HOURS = 12


def _next_shift(day, shift):
    order = [Shift.MORNING, Shift.AFTERNOON, Shift.NIGHT]
    index = order.index(shift)
    if index == len(order) - 1:
        return day + datetime.timedelta(days=1), order[0]
    return day, order[index + 1]


def _iso(moment):
    return timezone.localtime(moment).isoformat() if moment else None


def build_pack(user, now=None):
    now = now or timezone.now()
    config = SystemConfig.get()
    day, shift = resolve_shift(now)
    shifts = [(day, shift), _next_shift(day, shift)]
    guests = list(guests_in_care().prefetch_related("allergies", "contacts", "diagnoses"))
    guest_ids = {g.pk for g in guests}

    doses = []
    for shift_day, code in shifts:
        start, end = shift_bounds(shift_day, code)
        for dose in scheduled_doses(shift_day, code, guests):
            adm = dose.administration
            doses.append({
                "therapy": dose.therapy.pk, "guest": dose.guest.pk, "day": dose.day.isoformat(),
                "time": dose.time.strftime("%H:%M"), "moment": _iso(dose.moment), "shift": code,
                "shift_day": shift_day.isoformat(), "drug": str(dose.therapy.drug),
                "dose": dose.therapy.dose_display, "route": dose.therapy.get_route_display(),
                "instructions": dose.therapy.instructions,
                "done": {"status": adm.get_status_display(), "at": _iso(adm.occurred_at),
                         "by": str(adm.created_by or "")} if adm else None,
            })

    since = now - datetime.timedelta(hours=24)
    sos_given = {}
    for adm in TherapyAdministration.objects.filter(is_sos=True, occurred_at__gte=since,
                                                    status=TherapyAdministration.Status.GIVEN).order_by("occurred_at"):
        sos_given.setdefault(adm.therapy_id, []).append(_iso(adm.occurred_at))
    sos = []
    for therapy in Therapy.objects.filter(status=Therapy.Status.ACTIVE, is_sos=True,
                                          guest_id__in=guest_ids).select_related("drug"):
        sos.append({
            "therapy": therapy.pk, "guest": therapy.guest_id, "drug": str(therapy.drug), "dose": therapy.dose_display,
            "route": therapy.get_route_display(), "indication": therapy.sos_indication,
            "max_daily": therapy.sos_max_daily, "min_interval_hours": therapy.sos_min_interval_hours,
            "given_24h": sos_given.get(therapy.pk, []),
        })

    from fasas.protocols.engine import open_activations

    protocols = []
    for activation in open_activations().prefetch_related("action_logs"):
        protocols.append({
            "guest": activation.guest_id, "name": activation.protocol.name, "summary": activation.trigger_summary,
            "pending": [a["label"] for a in activation.actions_status() if not a["log"]],
        })

    latest = {}
    from fasas.clinical.models import ParameterReading

    for reading in ParameterReading.objects.filter(guest_id__in=guest_ids, occurred_at__gte=now - datetime.timedelta(days=7)
                                                   ).select_related("parameter_type").order_by("-occurred_at"):
        latest.setdefault((reading.guest_id, reading.parameter_type_id), {
            "guest": reading.guest_id, "type": reading.parameter_type.name, "value": reading.display_value,
            "at": _iso(reading.occurred_at), "out_of_range": reading.out_of_range,
        })

    return {
        "version": 1,
        "generated_at": _iso(now),
        "expires_at": _iso(now + datetime.timedelta(hours=PACK_HOURS)),
        "user": {"id": user.pk, "username": user.username, "name": user.get_full_name() or user.username},
        "community": config.community.name,
        "idle_minutes": config.session_timeout_minutes,
        "shifts": [{"day": d.isoformat(), "code": c, "label": Shift(c).label,
                    "start": _iso(shift_bounds(d, c)[0]), "end": _iso(shift_bounds(d, c)[1])} for d, c in shifts],
        "guests": [{
            "id": g.pk, "name": f"{g.last_name} {g.first_name}", "room": g.room, "age": g.age,
            "status": g.get_status_display(), "present": g.status == g.Status.ACTIVE,
            "diet": " · ".join(x for x in (g.diet, g.diet_texture) if x),
            "tags": [{"name": t.name, "color": t.color, "alert": t.alert_message} for t in g.tags.all()],
            "allergies": [{"substance": a.substance, "severity": a.get_severity_display(), "reaction": a.reaction,
                           "kind": a.get_kind_display()} for a in g.allergies.all()],
            "diagnoses": [d.description for d in g.diagnoses.all() if d.active][:6],
            "contacts": [{"name": c.name, "relationship": c.relationship or c.get_kind_display(), "phone": c.phone}
                         for c in g.contacts.all() if c.is_emergency_contact],
            "doctor": {"name": g.general_practitioner, "phone": g.general_practitioner_phone},
        } for g in guests],
        "doses": doses,
        "sos": sos,
        "protocols": protocols,
        "parameters": list(latest.values()),
        "parameter_types": [{"id": p.pk, "name": p.name, "unit": p.unit, "bp": p.kind == ParameterType.Kind.BLOOD_PRESSURE,
                             "min": float(p.min_normal) if p.min_normal is not None else None,
                             "max": float(p.max_normal) if p.max_normal is not None else None}
                            for p in ParameterType.objects.filter(active=True)],
        "event_types": [{"code": c, "label": label} for c, label in ClinicalEvent.EventType.choices],
        "severities": [{"code": c, "label": label} for c, label in ClinicalEvent.Severity.choices],
        "administration_statuses": [{"code": c, "label": label} for c, label in TherapyAdministration.Status.choices],
        "permissions": {
            "administration": user.has_perm("clinical.add_therapyadministration"),
            "parameter": user.has_perm("clinical.add_parameterreading"),
            "diary": user.has_perm("daily.add_diaryentry"),
            "event": user.has_perm("clinical.add_clinicalevent"),
        },
    }
