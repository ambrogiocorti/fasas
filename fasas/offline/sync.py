"""
Sincronizzazione delle registrazioni fatte senza rete.

Ogni registrazione porta l'identificativo generato dal dispositivo (UUID): ripetere l'invio non crea
duplicati. Si applicano le stesse regole dell'uso online, con due differenze dichiarate:
- data e ora sono quelle in cui l'operatore ha registrato sul dispositivo (non quelle dell'invio);
- se nel frattempo il turno è stato chiuso (es. chiusura automatica durante l'interruzione) la
  registrazione viene comunque accettata, segnalata come tardiva e notificata al coordinatore:
  un farmaco somministrato non può sparire perché mancava la rete.
L'audit log riporta origine «offline» e la motivazione.
"""
import datetime
import uuid as uuidlib
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from fasas.audit.context import audit_context
from fasas.clinical.models import ClinicalEvent, ParameterReading, ParameterType, Therapy, TherapyAdministration
from fasas.clinical.services import register_administration, sos_limits_warnings
from fasas.core.shifts import resolve_shift
from fasas.daily.models import DiaryEntry
from fasas.daily.services import is_shift_closed
from fasas.guests.models import Guest

from .models import OfflineRecord

MAX_AGE = datetime.timedelta(hours=72)
MAX_BATCH = 500

PERMISSIONS = {
    OfflineRecord.Kind.ADMINISTRATION: "clinical.add_therapyadministration",
    OfflineRecord.Kind.SOS: "clinical.add_therapyadministration",
    OfflineRecord.Kind.PARAMETER: "clinical.add_parameterreading",
    OfflineRecord.Kind.DIARY: "daily.add_diaryentry",
    OfflineRecord.Kind.EVENT: "clinical.add_clinicalevent",
}


class Rejected(Exception):
    def __init__(self, message, status=OfflineRecord.Status.REJECTED):
        super().__init__(message)
        self.status = status


def _text(data, key, limit):
    return str(data.get(key) or "").strip()[:limit]


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        raise Rejected("valore numerico non valido") from None


def _guest(data):
    guest = Guest.objects.filter(pk=data.get("guest")).first()
    if guest is None:
        raise Rejected("ospite non trovato")
    if guest.is_archived:
        raise Rejected("la cartella dell'ospite è stata archiviata")
    return guest


def _administration(user, data, when):
    therapy = Therapy.objects.select_related("guest", "drug").filter(pk=data.get("therapy")).first()
    if therapy is None or therapy.is_sos:
        raise Rejected("terapia non trovata")
    try:
        day = datetime.date.fromisoformat(data["day"])
        at = datetime.datetime.strptime(data["time"], "%H:%M").time()
    except (KeyError, TypeError, ValueError):
        raise Rejected("dose programmata non valida") from None
    status = data.get("status") or TherapyAdministration.Status.GIVEN
    if status not in TherapyAdministration.Status.values:
        raise Rejected("esito non valido")
    existing = TherapyAdministration.objects.filter(therapy=therapy, scheduled_date=day, scheduled_time=at).first()
    if existing:
        raise Rejected(f"dose già registrata da {existing.created_by or 'altro operatore'} alle "
                       f"{timezone.localtime(existing.occurred_at):%H:%M} ({existing.get_status_display().lower()})",
                       OfflineRecord.Status.CONFLICT)
    if therapy.status != Therapy.Status.ACTIVE:
        raise Rejected("la terapia è stata sospesa o terminata nel frattempo")
    adm = register_administration(therapy, user, status=status, scheduled_date=day, scheduled_time=at,
                                  occurred_at=when, notes=_text(data, "notes", 500))
    return therapy.guest, adm, ""


def _sos(user, data, when):
    therapy = Therapy.objects.select_related("guest", "drug").filter(pk=data.get("therapy"), is_sos=True).first()
    if therapy is None:
        raise Rejected("farmaco SOS non trovato")
    reason = _text(data, "reason", 1000)
    if not reason:
        raise Rejected("manca il motivo della somministrazione SOS")
    warnings = sos_limits_warnings(therapy, when)
    adm = register_administration(therapy, user, occurred_at=when, notes=_text(data, "notes", 500),
                                  dose_given=_text(data, "dose", 60), sos_reason=reason)
    return therapy.guest, adm, " ".join(warnings)


def _parameter(user, data, when):
    guest = _guest(data)
    ptype = ParameterType.objects.filter(pk=data.get("parameter_type"), active=True).first()
    if ptype is None:
        raise Rejected("tipo di parametro non trovato")
    value = _decimal(data.get("value"))
    if value is None:
        raise Rejected("manca il valore")
    value_2 = _decimal(data.get("value_2"))
    reading = ParameterReading.objects.create(guest=guest, parameter_type=ptype, value=value, value_2=value_2,
                                              occurred_at=when, notes=_text(data, "notes", 255))
    return guest, reading, ""


def _diary(user, data, when):
    guest = _guest(data)
    text = _text(data, "text", 5000)
    if not text:
        raise Rejected("nota vuota")
    entry = DiaryEntry.objects.create(guest=guest, text=text, is_relevant=bool(data.get("relevant")), occurred_at=when)
    return guest, entry, ""


def _event(user, data, when):
    guest = _guest(data)
    event_type = data.get("event_type")
    severity = data.get("severity") or ClinicalEvent.Severity.LOW
    if event_type not in ClinicalEvent.EventType.values or severity not in ClinicalEvent.Severity.values:
        raise Rejected("tipo o gravità dell'evento non validi")
    description = _text(data, "description", 5000)
    if not description:
        raise Rejected("manca la descrizione")
    try:
        duration = int(data["duration_minutes"]) if data.get("duration_minutes") not in (None, "") else None
    except (TypeError, ValueError):
        raise Rejected("durata non valida") from None
    event = ClinicalEvent.objects.create(
        guest=guest, event_type=event_type, severity=severity, description=description, duration_minutes=duration,
        actions_taken=_text(data, "actions_taken", 5000), doctor_notified=bool(data.get("doctor_notified")),
        emergency_services_called=bool(data.get("emergency_services_called")), occurred_at=when,
    )
    return guest, event, ""


HANDLERS = {
    OfflineRecord.Kind.ADMINISTRATION: _administration,
    OfflineRecord.Kind.SOS: _sos,
    OfflineRecord.Kind.PARAMETER: _parameter,
    OfflineRecord.Kind.DIARY: _diary,
    OfflineRecord.Kind.EVENT: _event,
}


def _occurred_at(data, now):
    when = parse_datetime(str(data.get("occurred_at") or ""))
    if when is None:
        raise Rejected("data e ora mancanti")
    if timezone.is_naive(when):
        when = timezone.make_aware(when)
    if when > now + datetime.timedelta(minutes=10):
        raise Rejected("data e ora nel futuro: controllare l'orologio del dispositivo")
    if when < now - MAX_AGE:
        raise Rejected("registrazione più vecchia di 72 ore: inserirla a mano con le regole di modifica")
    return when


def _result(record):
    return {"uuid": str(record.uuid), "status": record.status, "message": record.message,
            "label": record.object_label}


def _handle(user, data, kind, now):
    """Esegue la registrazione; restituisce (esito, messaggio, ospite, descrizione, data e ora)."""
    guest, label, when = None, "", now
    try:
        if kind not in HANDLERS:
            raise Rejected("tipo di registrazione sconosciuto")
        if not user.has_perm(PERMISSIONS[kind]):
            raise Rejected("non hai il permesso per questa registrazione")
        when = _occurred_at(data, now)
        day, shift = resolve_shift(when)
        late = is_shift_closed(day, shift)
        reason = (f"Registrazione senza rete del {timezone.localtime(when):%d/%m/%Y %H:%M}, sincronizzata il "
                  f"{timezone.localtime(now):%d/%m/%Y %H:%M}" + (" (turno già chiuso)" if late else ""))
        with transaction.atomic(), audit_context(source="offline", reason=reason):
            guest, obj, warning = HANDLERS[kind](user, data, when)
    except Rejected as exc:
        return exc.status, str(exc), guest, label, when
    except IntegrityError:
        return OfflineRecord.Status.CONFLICT, "registrazione già presente", guest, label, when
    if late:
        return (OfflineRecord.Status.LATE, ("turno già chiuso: registrazione accettata come tardiva. " + warning).strip(),
                guest, str(obj)[:255], when)
    return OfflineRecord.Status.OK, warning, guest, str(obj)[:255], when


def process_record(user, data, now):
    try:
        record_uuid = uuidlib.UUID(str(data.get("uuid")))
    except ValueError:
        return {"uuid": str(data.get("uuid")), "status": "rejected", "message": "identificativo non valido"}
    existing = OfflineRecord.objects.filter(uuid=record_uuid).first()
    if existing is None:
        kind = data.get("kind")
        try:
            with transaction.atomic():
                status, message, guest, label, when = _handle(user, data, kind, now)
                if guest is None and str(data.get("guest") or "").isdigit():
                    guest = Guest.objects.filter(pk=data["guest"]).first()
                existing = OfflineRecord.objects.create(
                    uuid=record_uuid, user=user, kind=kind if kind in HANDLERS else OfflineRecord.Kind.OTHER,
                    guest=guest, occurred_at=when, status=status, message=message[:500], payload=data,
                    object_label=label,
                )
        except IntegrityError:  # stesso invio arrivato due volte in parallelo: vale il primo
            existing = OfflineRecord.objects.get(uuid=record_uuid)
    if existing.user_id != user.pk:
        return {"uuid": str(record_uuid), "status": "rejected", "message": "registrazione di un altro utente"}
    return _result(existing)


def sync(user, records, now=None):
    now = now or timezone.now()
    results = [process_record(user, data, now) for data in records[:MAX_BATCH] if isinstance(data, dict)]
    problems = [r for r in results if r["status"] != OfflineRecord.Status.OK]
    if problems:
        from fasas.notifications.services import notify

        notify("offline_sync", f"Registrazioni senza rete da verificare ({len(problems)})",
               f"{user} ha sincronizzato {len(results)} registrazioni fatte senza rete: {len(problems)} da verificare "
               "(turno chiuso, dose già registrata o dati non validi).",
               link=reverse("offline:records"), level="warning")
    return results
