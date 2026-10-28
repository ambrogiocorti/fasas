"""
Audit log obbligatorio e non cancellabile (sezione 16).

Garanzie:
- a livello applicativo save() su record esistente e delete() sollevano eccezione;
- su PostgreSQL un trigger rifiuta UPDATE, DELETE e TRUNCATE (migrazione 0002);
- ogni voce contiene l'hash della precedente: un'alterazione diretta sul database
  rompe la catena ed è rilevata da "manage.py audit_verify".
"""
import hashlib
import json

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models, transaction
from django.utils import timezone


class ImmutableRecordError(Exception):
    pass


AUDIT_CHAIN_LOCK = 727274


def lock_audit_chain():
    """
    Lock di transazione che serializza la scrittura della catena di hash (solo PostgreSQL).
    Le funzioni che bloccano righe con select_for_update e poi scrivono l'audit lo acquisiscono
    per prime, così l'ordine dei lock è sempre lo stesso e non si creano deadlock.
    """
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [AUDIT_CHAIN_LOCK])


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableRecordError("I registri di audit non possono essere modificati.")

    def delete(self):
        raise ImmutableRecordError("I registri di audit non possono essere cancellati.")


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Inserimento"
        UPDATE = "update", "Modifica"
        DELETE = "delete", "Cancellazione"
        VOID = "void", "Annullamento"
        VIEW = "view", "Consultazione"
        DOWNLOAD = "download", "Download"
        EXPORT = "export", "Esportazione"
        SIGN = "sign", "Firma digitale"
        CLOSE = "close", "Chiusura turno"
        REOPEN = "reopen", "Riapertura"
        ARCHIVE = "archive", "Archiviazione"
        BACKUP = "backup", "Backup"
        RESTORE = "restore", "Ripristino"
        CONFIG = "config", "Configurazione"
        PERMISSION = "permission", "Permessi"
        SYSTEM = "system", "Sistema"

    timestamp = models.DateTimeField("data e ora", db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="utente", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    username = models.CharField("nome utente", max_length=150, blank=True)
    action = models.CharField("azione", max_length=20, choices=Action.choices, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, null=True, blank=True)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    object_repr = models.CharField("oggetto", max_length=255, blank=True)
    guest_id = models.BigIntegerField("ospite", null=True, blank=True, db_index=True)
    changes = models.JSONField("modifiche", default=dict, blank=True)
    reason = models.TextField("motivazione", blank=True)
    ip_address = models.CharField("IP", max_length=64, blank=True)
    source = models.CharField("origine", max_length=20, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, unique=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = "voce di audit"
        verbose_name_plural = "audit log"
        ordering = ["-id"]
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.timestamp:%d/%m/%Y %H:%M} {self.username} {self.get_action_display()} {self.object_repr}"

    def payload(self):
        return {
            "prev": self.prev_hash,
            "ts": self.timestamp.isoformat(),
            "user": self.user_id,
            "username": self.username,
            "action": self.action,
            "ct": self.content_type_id,
            "oid": self.object_id,
            "repr": self.object_repr,
            "guest": self.guest_id,
            "changes": self.changes,
            "reason": self.reason,
            "ip": self.ip_address,
        }

    def compute_hash(self):
        data = json.dumps(self.payload(), sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(data.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableRecordError("I registri di audit non possono essere modificati.")
        with transaction.atomic():
            lock_audit_chain()
            last = AuditLog.objects.order_by("-id").values_list("hash", flat=True).first()
            self.prev_hash = last or ""
            if self.timestamp is None:
                self.timestamp = timezone.now()
            self.hash = self.compute_hash()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("I registri di audit non possono essere cancellati.")
