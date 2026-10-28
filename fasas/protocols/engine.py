"""
Motore dei protocolli automatici (sezione 8).

Ogni regola è valutata:
- in tempo reale quando si registra un dato collegato (parametro, evento, SOS, evacuazione);
- periodicamente dal job "protocols" per le regole basate sul tempo (giorni senza evacuazione).

Se esiste già un'attivazione aperta dello stesso protocollo per lo stesso ospite non se ne crea
un'altra: l'attivazione aperta viene aggiornata con il nuovo dato.
"""
import datetime
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Protocol, ProtocolActivation

logger = logging.getLogger("fasas.protocols")


def _protocols(kind, guest):
    return [p for p in Protocol.objects.filter(kind=kind, active=True).prefetch_related("tags") if p.applies_to(guest)]


@transaction.atomic
def activate(protocol, guest, summary, data=None):
    from fasas.audit.models import lock_audit_chain
    from fasas.notifications.services import notify

    lock_audit_chain()
    open_activation = ProtocolActivation.objects.select_for_update().filter(
        protocol=protocol, guest=guest, status__in=ProtocolActivation.OPEN_STATES
    ).first()
    if open_activation is not None:
        history = open_activation.trigger_data.setdefault("updates", [])
        history.append({"at": timezone.now().isoformat(), "summary": summary, **(data or {})})
        open_activation.trigger_data["updates"] = history[-20:]
        open_activation.save(update_fields=["trigger_data"])
        return open_activation, False

    activation = ProtocolActivation.objects.create(
        protocol=protocol, guest=guest, trigger_summary=summary[:255], trigger_data=data or {}
    )
    actions = "\n".join(f"• {a}" for a in protocol.action_list)
    notify(
        "protocol_activated",
        f"Protocollo «{protocol.name}» attivato – {guest}",
        f"{summary}\nAzioni richieste:\n{actions}",
        link=activation.get_absolute_url(), guest=guest, level=protocol.severity,
        roles=protocol.notify_roles or None, dedup_key=f"protocol-{activation.pk}",
    )
    logger.info("Protocollo %s attivato per ospite %s: %s", protocol.pk, guest.pk, summary)
    return activation, True


def resolve(activation, user=None, notes="", automatic=False, status=ProtocolActivation.Status.RESOLVED):
    activation.status = status
    activation.resolved_at = timezone.now()
    activation.resolved_by = user
    activation.resolution_notes = notes
    activation.auto_resolved = automatic
    activation.save()
    return activation


# --- Hook in tempo reale -----------------------------------------------------------------

def on_parameter_reading(reading):
    guest = reading.guest
    code = reading.parameter_type.code
    value = Decimal(reading.value)
    for protocol in _protocols(Protocol.Kind.FEVER, guest):
        if code == protocol.param("parameter") and value >= Decimal(str(protocol.param("threshold"))):
            activate(protocol, guest, f"Temperatura {reading.display_value} (soglia {protocol.param('threshold')} °C)",
                     {"reading": reading.pk, "value": str(value)})
    for protocol in _protocols(Protocol.Kind.GLYCEMIA, guest):
        if code != protocol.param("parameter"):
            continue
        low, high = Decimal(str(protocol.param("min"))), Decimal(str(protocol.param("max")))
        if value < low:
            activate(protocol, guest, f"Ipoglicemia: {reading.display_value} (minimo {low})",
                     {"reading": reading.pk, "value": str(value), "direction": "low"})
        elif value > high:
            activate(protocol, guest, f"Iperglicemia: {reading.display_value} (massimo {high})",
                     {"reading": reading.pk, "value": str(value), "direction": "high"})


def on_clinical_event(event):
    from fasas.clinical.models import ClinicalEvent

    guest = event.guest
    if event.event_type == ClinicalEvent.EventType.SEIZURE:
        for protocol in _protocols(Protocol.Kind.SEIZURE, guest):
            min_duration = int(protocol.param("min_duration_minutes") or 0)
            if (event.duration_minutes or 0) >= min_duration:
                duration = f", durata {event.duration_minutes} min" if event.duration_minutes else ""
                activate(protocol, guest, f"Crisi epilettica registrata{duration}", {"event": event.pk})
    if event.event_type in (ClinicalEvent.EventType.AGITATION, ClinicalEvent.EventType.AGGRESSION):
        for protocol in _protocols(Protocol.Kind.AGITATION, guest):
            window = datetime.timedelta(hours=int(protocol.param("window_hours")))
            count = ClinicalEvent.objects.filter(
                guest=guest, event_type__in=[ClinicalEvent.EventType.AGITATION, ClinicalEvent.EventType.AGGRESSION],
                occurred_at__gte=event.occurred_at - window, occurred_at__lte=event.occurred_at,
            ).count()
            if count >= int(protocol.param("events")):
                activate(protocol, guest, f"{count} episodi di agitazione nelle ultime {protocol.param('window_hours')} ore",
                         {"event": event.pk, "count": count})


def on_sos_administration(administration):
    from fasas.clinical.models import TherapyAdministration

    guest = administration.guest
    for protocol in _protocols(Protocol.Kind.SOS, guest):
        window = datetime.timedelta(hours=int(protocol.param("window_hours")))
        count = TherapyAdministration.objects.filter(
            guest=guest, is_sos=True, status=TherapyAdministration.Status.GIVEN,
            occurred_at__gte=administration.occurred_at - window,
        ).count()
        if count >= int(protocol.param("count")):
            activate(protocol, guest, f"{count} farmaci SOS nelle ultime {protocol.param('window_hours')} ore",
                     {"administration": administration.pk, "count": count})


def on_evacuation(record):
    """Un'evacuazione registrata chiude automaticamente il protocollo evacuazione aperto."""
    if not record.outcome:
        return
    for activation in ProtocolActivation.objects.filter(
        guest=record.guest, protocol__kind=Protocol.Kind.EVACUATION, status__in=ProtocolActivation.OPEN_STATES,
    ):
        resolve(activation, record.created_by, "Evacuazione registrata: protocollo chiuso automaticamente.", automatic=True)


# --- Controlli periodici -----------------------------------------------------------------

def check_evacuation(guest, today=None):
    from fasas.daily.services import days_since_last_evacuation

    activations = []
    days, last = days_since_last_evacuation(guest, today)
    for protocol in _protocols(Protocol.Kind.EVACUATION, guest):
        threshold = int(protocol.param("days"))
        if days >= threshold:
            last_text = f"ultima il {timezone.localtime(last.occurred_at):%d/%m/%Y}" if last else "nessuna registrata"
            activation, _ = activate(protocol, guest, f"Nessuna evacuazione da {days} giorni ({last_text})",
                                     {"days": days})
            activations.append(activation)
    return activations


def run_periodic_checks(today=None):
    from fasas.guests.models import Guest

    count = 0
    for guest in Guest.objects.filter(status=Guest.Status.ACTIVE).prefetch_related("tags"):
        count += len(check_evacuation(guest, today))
    return {"evacuation_activations": count}


def open_activations(guest=None):
    qs = ProtocolActivation.objects.filter(status__in=ProtocolActivation.OPEN_STATES).select_related("protocol", "guest")
    if guest is not None:
        qs = qs.filter(guest=guest)
    return qs
