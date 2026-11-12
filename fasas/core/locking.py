"""
Regole di blocco delle modifiche ai dati sanitari (sezioni 17, 18 e 25 della specifica).

Ordine di valutazione:
1. cartella ospite archiviata  -> sempre bloccato
2. turno chiuso (blocco giornata) -> sempre bloccato
3. entro la finestra di modifica -> libero
4. oltre la finestra -> secondo la politica configurata
"""
import datetime
from dataclasses import dataclass

from django.utils import timezone

from .models import SystemConfig


@dataclass
class EditDecision:
    allowed: bool
    reason_required: bool = False
    message: str = ""


def guest_of(obj):
    from fasas.guests.models import Guest

    if isinstance(obj, Guest):
        return obj
    return getattr(obj, "guest", None)


def edit_decision(obj, user, now=None, config=None):
    config = config or SystemConfig.get()
    now = now or timezone.now()

    guest = guest_of(obj)
    if guest is not None and guest.is_archived:
        return EditDecision(False, message="La cartella dell'ospite è archiviata: le modifiche sono bloccate.")

    if getattr(obj, "is_voided", False):
        return EditDecision(False, message="La registrazione è stata annullata e non può essere modificata.")

    shift_date = getattr(obj, "shift_date", None)
    shift = getattr(obj, "shift", None)
    if shift_date and shift:
        from fasas.daily.services import is_shift_closed

        if is_shift_closed(shift_date, shift):
            return EditDecision(False, message="Il turno è stato chiuso: i dati non sono più modificabili.")

    created_at = getattr(obj, "created_at", None)
    if created_at is None or now - created_at <= datetime.timedelta(hours=config.edit_window_hours):
        return EditDecision(True)

    hours = config.edit_window_hours
    policy = config.edit_lock_policy
    if policy == SystemConfig.EditLockPolicy.WITHIN_WINDOW:
        return EditDecision(False, message=f"Il dato è modificabile solo entro {hours} ore dall'inserimento.")
    if policy == SystemConfig.EditLockPolicy.AFTER_WINDOW_COORDINATOR:
        if user.has_perm("core.edit_after_window"):
            return EditDecision(True, reason_required=True, message=f"Modifica oltre {hours} ore: indicare la motivazione.")
        return EditDecision(False, message=f"Dopo {hours} ore solo il coordinatore può modificare questo dato.")
    return EditDecision(True, reason_required=True, message=f"Modifica oltre {hours} ore: la motivazione è obbligatoria.")


def creation_decision(guest, occurred_at=None, user=None):
    """Una nuova registrazione non può cadere in un turno chiuso né su una cartella archiviata."""
    from fasas.daily.services import is_shift_closed

    from .shifts import resolve_shift

    if guest is not None and guest.is_archived:
        return EditDecision(False, message="La cartella dell'ospite è archiviata: non è possibile inserire dati.")
    day, shift = resolve_shift(occurred_at)
    if is_shift_closed(day, shift):
        return EditDecision(False, message="Il turno di riferimento è chiuso: non è possibile inserire dati.")
    return EditDecision(True)
