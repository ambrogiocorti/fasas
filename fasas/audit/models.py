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
        DENIED = "denied", "Tentativo non autorizzato"

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


class AuditCheckpoint(models.Model):
    """
    Punto di controllo dell'audit log (vedi fasas.audit.anchoring): esito della verifica completa e impronta
    dell'ultima voce, con marca temporale RFC 3161 se è configurata una TSA. In sola aggiunta.
    """

    created_at = models.DateTimeField("data e ora", default=timezone.now, db_index=True)
    source = models.CharField("origine", max_length=20, default="job")
    entries = models.PositiveIntegerField("voci verificate", default=0)
    chain_ok = models.BooleanField("integro")
    broken_at = models.BigIntegerField("prima voce non valida", null=True, blank=True)
    mismatched_checkpoints = models.JSONField("punti di controllo non più corrispondenti", default=list, blank=True)
    last_entry_id = models.BigIntegerField("ultima voce", null=True, blank=True)
    head_hash = models.CharField("impronta dell'ultima voce", max_length=64, blank=True)
    timestamp_token = models.BinaryField("marca temporale (RFC 3161)", null=True, blank=True)
    timestamp_time = models.DateTimeField("ora della marca", null=True, blank=True)
    tsa_url = models.CharField("TSA", max_length=255, blank=True)
    timestamp_error = models.CharField("errore della marca", max_length=255, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name = "punto di controllo dell'audit"
        verbose_name_plural = "punti di controllo dell'audit"
        ordering = ["-id"]
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.created_at:%d/%m/%Y %H:%M} – {'integro' if self.chain_ok else 'NON integro'}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableRecordError("I punti di controllo dell'audit non possono essere modificati.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("I punti di controllo dell'audit non possono essere cancellati.")

    def message(self):
        from .anchoring import anchor_message

        return anchor_message(self.last_entry_id, self.head_hash, self.entries)

    @property
    def timestamped(self):
        return bool(self.timestamp_token)
