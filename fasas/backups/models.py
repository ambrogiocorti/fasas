from django.conf import settings
from django.db import models
from django.utils import timezone


class BackupRecord(models.Model):
    class Kind(models.TextChoices):
        AUTO = "auto", "Automatico"
        MANUAL = "manual", "Manuale"

    class Status(models.TextChoices):
        RUNNING = "running", "In corso"
        OK = "ok", "Completato"
        FAILED = "failed", "Fallito"

    created_at = models.DateTimeField("avviato il", default=timezone.now, db_index=True)
    finished_at = models.DateTimeField("completato il", null=True, blank=True)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.AUTO)
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.RUNNING)
    filename = models.CharField("file", max_length=255, blank=True)
    size = models.PositiveBigIntegerField("dimensione", default=0)
    sha256 = models.CharField("impronta SHA-256 del file cifrato", max_length=64, blank=True)
    db_format = models.CharField("formato database", max_length=20, blank=True)
    includes_media = models.BooleanField("include i file", default=True)
    verified_at = models.DateTimeField("verificato il", null=True, blank=True)
    verify_ok = models.BooleanField("verifica superata", null=True)
    error = models.TextField("errore", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")
    deleted_at = models.DateTimeField("eliminato per conservazione il", null=True, blank=True)

    class Meta:
        verbose_name = "backup"
        verbose_name_plural = "backup"
        ordering = ["-created_at"]
        permissions = [("manage_backup", "Può eseguire, verificare e scaricare i backup")]

    def __str__(self):
        return f"Backup {self.created_at:%d/%m/%Y %H:%M} ({self.get_status_display()})"

    @property
    def path(self):
        return settings.FASAS_BACKUP_DIR / self.filename if self.filename else None
