import datetime
import decimal
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save

from .context import current_ip, current_reason, current_source, current_user
from .models import AuditLog

logger = logging.getLogger("fasas.audit")

# modello -> opzioni di tracciamento
_REGISTRY = {}

ALWAYS_EXCLUDED = {"updated_at", "updated_by"}


def _plain(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    return str(value)


def _field_values(instance, exclude):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in exclude or field.name in ALWAYS_EXCLUDED:
            continue
        values[field.name] = _plain(getattr(instance, field.attname))
    return values


def _guest_id(instance, guest_field):
    from fasas.guests.models import Guest

    if isinstance(instance, Guest):
        return instance.pk
    if not guest_field:
        return None
    obj = instance
    for part in guest_field.split("__"):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj.pk if isinstance(obj, models.Model) else obj


def log_event(action, obj=None, *, user=None, guest=None, changes=None, reason=None, repr_text=None):
    """Scrive una voce di audit esplicita (consultazioni, download, esportazioni, firme...)."""
    user = user or current_user()
    content_type = ContentType.objects.get_for_model(obj, for_concrete_model=False) if obj is not None else None
    if guest is None and obj is not None:
        options = _REGISTRY.get(type(obj), {})
        guest_id = _guest_id(obj, options.get("guest_field", "guest"))
    else:
        guest_id = guest.pk if isinstance(guest, models.Model) else guest
    return AuditLog.objects.create(
        user=user if getattr(user, "pk", None) else None,
        username=getattr(user, "username", "") or "sistema",
        action=action,
        content_type=content_type,
        object_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
        object_repr=(repr_text or (str(obj) if obj is not None else ""))[:255],
        guest_id=guest_id,
        changes=_plain(changes or {}),
        reason=reason if reason is not None else current_reason(),
        ip_address=current_ip(),
        source=current_source(),
    )


def _pre_save(sender, instance, raw=False, **kwargs):
    if raw:  # caricamento da backup/fixture: non è una modifica da tracciare
        return
    options = _REGISTRY[sender]
    instance._audit_old = None
    if instance.pk is not None:
        old = sender._base_manager.filter(pk=instance.pk).first()
        if old is not None:
            instance._audit_old = _field_values(old, options["exclude"])
    user = current_user()
    if user is not None and getattr(user, "pk", None):
        if hasattr(instance, "updated_by_id"):
            instance.updated_by = user
        if instance.pk is None and hasattr(instance, "created_by_id") and instance.created_by_id is None:
            instance.created_by = user


def _post_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    options = _REGISTRY[sender]
    new = _field_values(instance, options["exclude"])
    old = getattr(instance, "_audit_old", None)
    if created or old is None:
        changes = {name: [None, value] for name, value in new.items() if value not in (None, "", [], {})}
        action = AuditLog.Action.CREATE
    else:
        changes = {name: [old.get(name), value] for name, value in new.items() if old.get(name) != value}
        if not changes:
            return
        action = AuditLog.Action.VOID if "voided_at" in changes and changes["voided_at"][0] is None else AuditLog.Action.UPDATE
    for name in options["redact"]:
        if name in changes:
            changes[name] = ["***", "***"]
    log_event(action, instance, changes=changes)


def _post_delete(sender, instance, **kwargs):
    options = _REGISTRY[sender]
    old = _field_values(instance, options["exclude"])
    log_event(AuditLog.Action.DELETE, instance, changes={k: [v, None] for k, v in old.items()})


def register(model, exclude=(), redact=(), guest_field="guest"):
    """Traccia ogni inserimento, modifica e cancellazione del modello con valore precedente e nuovo."""
    _REGISTRY[model] = {"exclude": set(exclude), "redact": set(redact), "guest_field": guest_field}
    uid = f"fasas-audit-{model._meta.label_lower}"
    pre_save.connect(_pre_save, sender=model, dispatch_uid=f"{uid}-pre")
    post_save.connect(_post_save, sender=model, dispatch_uid=f"{uid}-post")
    post_delete.connect(_post_delete, sender=model, dispatch_uid=f"{uid}-del")
    return model


def registered_models():
    return list(_REGISTRY)


def verify_chain():
    """Ricalcola la catena di hash. Restituisce (ok, numero_voci, primo_id_non_valido)."""
    previous = ""
    count = 0
    for entry in AuditLog.objects.order_by("id").iterator(chunk_size=2000):
        count += 1
        if entry.prev_hash != previous or entry.compute_hash() != entry.hash:
            return False, count, entry.pk
        previous = entry.hash
    return True, count, None


def scheduled_chain_verification():
    """Job notturno: verifica completa, controllo dei punti precedenti, nuovo punto di controllo con marca."""
    from .anchoring import create_checkpoint

    checkpoint = create_checkpoint("job")
    return {"ok": checkpoint.chain_ok, "entries": checkpoint.entries, "broken_at": checkpoint.broken_at,
            "timestamped": checkpoint.timestamped}
