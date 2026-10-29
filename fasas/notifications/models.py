from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationKind(models.TextChoices):
    PROTOCOL = "protocol_activated", "Protocollo attivato"
    EMERGENCY = "emergency_event", "Evento critico (modalità emergenza)"
    CRITICAL_EVENT = "critical_event", "Evento sanitario grave"
    STOCK_LOW = "stock_low", "Farmaco in esaurimento"
    STOCK_EXPIRING = "stock_expiring", "Farmaco in scadenza"
    APPOINTMENT_TOMORROW = "appointment_tomorrow", "Visita domani"
    APPOINTMENT_TODAY = "appointment_today", "Visita oggi"
    THERAPY_CONFLICT = "therapy_conflict", "Avvisi duplicati/interazioni farmaci"
    SOS_VALIDATION = "sos_validation", "Farmaco SOS da validare"
    PAI_REVIEW = "pai_review", "Revisione PAI in scadenza"
    CHECKLIST_MISSING = "checklist_missing", "Turno chiuso con attività mancanti"
    DOCUMENT_EXPIRING = "document_expiring", "Documento in scadenza"
    BACKUP = "backup", "Esito backup"
    AUDIT_BROKEN = "audit_chain_broken", "Integrità audit log"
    REPORT = "report_ready", "Report programmato generato"


DEFAULT_ROLES = {
    NotificationKind.PROTOCOL: ["coordinator", "operator", "doctor"],
    NotificationKind.EMERGENCY: ["coordinator", "doctor", "operator"],
    NotificationKind.CRITICAL_EVENT: ["coordinator", "doctor"],
    NotificationKind.STOCK_LOW: ["coordinator"],
    NotificationKind.STOCK_EXPIRING: ["coordinator"],
    NotificationKind.APPOINTMENT_TOMORROW: ["coordinator", "operator"],
    NotificationKind.APPOINTMENT_TODAY: ["coordinator", "operator"],
    NotificationKind.THERAPY_CONFLICT: ["coordinator", "doctor"],
    NotificationKind.SOS_VALIDATION: ["coordinator", "doctor"],
    NotificationKind.PAI_REVIEW: ["coordinator"],
    NotificationKind.CHECKLIST_MISSING: ["coordinator"],
    NotificationKind.DOCUMENT_EXPIRING: ["coordinator"],
    NotificationKind.BACKUP: ["admin"],
    NotificationKind.AUDIT_BROKEN: ["admin"],
    NotificationKind.REPORT: ["coordinator"],
}

# Una notifica arriva solo a chi può aprire ciò a cui rimanda, qualunque ruolo sia configurato.
REQUIRED_PERMISSION = {
    NotificationKind.PROTOCOL: "protocols.view_protocolactivation",
    NotificationKind.EMERGENCY: "clinical.view_clinicalevent",
    NotificationKind.CRITICAL_EVENT: "clinical.view_clinicalevent",
    NotificationKind.STOCK_LOW: "pharmacy.view_stocklot",
    NotificationKind.STOCK_EXPIRING: "pharmacy.view_stocklot",
    NotificationKind.APPOINTMENT_TOMORROW: "appointments.view_appointment",
    NotificationKind.APPOINTMENT_TODAY: "appointments.view_appointment",
    NotificationKind.THERAPY_CONFLICT: "clinical.view_therapy",
    NotificationKind.SOS_VALIDATION: "clinical.validate_sos",
    NotificationKind.PAI_REVIEW: "pai.view_pai",
    NotificationKind.CHECKLIST_MISSING: "daily.view_shiftclosure",
    NotificationKind.DOCUMENT_EXPIRING: "documents.view_document",
    NotificationKind.BACKUP: "backups.manage_backup",
    NotificationKind.AUDIT_BROKEN: "audit.view_auditlog",
    NotificationKind.REPORT: "reports.view_generatedreport",
}


class NotificationSetting(models.Model):
    """Configurazione (amministratore): quali ruoli ricevono ogni tipo di notifica e se anche via email."""

    kind = models.CharField("tipo", max_length=40, choices=NotificationKind.choices, unique=True)
    enabled = models.BooleanField("attiva", default=True)
    roles = models.JSONField("ruoli destinatari", default=list, blank=True)
    send_email = models.BooleanField("invia anche email", default=False)

    class Meta:
        verbose_name = "impostazione notifiche"
        verbose_name_plural = "impostazioni notifiche"
        ordering = ["kind"]

    def __str__(self):
        return self.get_kind_display()


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Informazione"
        WARNING = "warning", "Attenzione"
        CRITICAL = "critical", "Critica"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField("tipo", max_length=40, choices=NotificationKind.choices)
    level = models.CharField("livello", max_length=10, choices=Level.choices, default=Level.INFO)
    title = models.CharField("titolo", max_length=200)
    message = models.TextField("messaggio", blank=True)
    link = models.CharField("collegamento", max_length=300, blank=True)
    guest = models.ForeignKey("guests.Guest", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    dedup_key = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "notifica"
        verbose_name_plural = "notifiche"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedup_key"], condition=~models.Q(dedup_key=""), name="unique_notification_dedup"
            )
        ]

    def __str__(self):
        return self.title

    @property
    def is_read(self):
        return self.read_at is not None
