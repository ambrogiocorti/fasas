from django.core.exceptions import PermissionDenied
from django.utils import timezone

from fasas.audit.context import audit_context
from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.models import SystemConfig

from .models import AdmissionEvent, Guest


class ArchivedGuestError(PermissionDenied):
    """È un PermissionDenied: se arriva a una vista diventa una pagina 403, mai un errore 500."""


def ensure_not_archived(guest):
    if guest.is_archived:
        raise ArchivedGuestError("La cartella dell'ospite è archiviata: le modifiche sono bloccate.")


def discharge_and_archive(guest, user, date, reason, destination=""):
    """Dimissione: la cartella viene archiviata, bloccata e conservata per gli anni configurati."""
    ensure_not_archived(guest)
    config = SystemConfig.get()
    with audit_context(reason=reason):
        AdmissionEvent.objects.create(
            guest=guest, kind=AdmissionEvent.Kind.DISCHARGE, date=date, notes=f"{reason}\nDestinazione: {destination}"
        )
        guest.status = Guest.Status.ARCHIVED
        guest.discharge_date = date
        guest.discharge_reason = reason
        guest.discharge_destination = destination
        guest.archived_at = timezone.now()
        guest.archived_by = user
        guest.retention_until = date.replace(year=date.year + config.archive_retention_years)
        guest.save()
        for therapy in guest.therapies.exclude(status="ended"):
            therapy.status = "ended"
            therapy.end_date = date
            therapy.save()
    log_event(AuditLog.Action.ARCHIVE, guest, reason=reason)
    return guest


def register_movement(guest, kind, date, notes=""):
    """Ricoveri e assenze cambiano lo stato dell'ospite; il rientro lo riporta presente."""
    ensure_not_archived(guest)
    event = AdmissionEvent.objects.create(guest=guest, kind=kind, date=date, notes=notes)
    if kind in (AdmissionEvent.Kind.HOSPITALIZATION, AdmissionEvent.Kind.ABSENCE):
        guest.status = Guest.Status.HOSPITALIZED
        guest.save(update_fields=["status", "updated_at", "updated_by"])
    elif kind == AdmissionEvent.Kind.RETURN:
        guest.status = Guest.Status.ACTIVE
        guest.save(update_fields=["status", "updated_at", "updated_by"])
    return event


def guests_in_care():
    """Ospiti per cui si registrano dati: presenti e temporaneamente assenti (non archiviati)."""
    return Guest.objects.exclude(status=Guest.Status.ARCHIVED).prefetch_related("tags")
