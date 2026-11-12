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
    offsite_key = models.CharField("copia fuori sede", max_length=500, blank=True)
    offsite_at = models.DateTimeField("copiato fuori sede il", null=True, blank=True)
    offsite_locked_until = models.DateTimeField("bloccato fino al", null=True, blank=True)
    offsite_error = models.TextField("errore copia fuori sede", blank=True)

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


class RestoreTest(models.Model):
    """Verbale di una prova di ripristino (consigliata ogni tre mesi): il backup si riapre davvero?"""

    class Result(models.TextChoices):
        OK = "ok", "Riuscita"
        PARTIAL = "partial", "Parziale"
        FAILED = "failed", "Fallita"

    created_at = models.DateTimeField("eseguita il", default=timezone.now, db_index=True)
    backup_name = models.CharField("backup provato", max_length=255, blank=True)
    backup_created_at = models.CharField("data del backup", max_length=40, blank=True)
    source = models.CharField("origine", max_length=20, blank=True, help_text="fuori sede o locale")
    result = models.CharField("esito", max_length=10, choices=Result.choices)
    steps = models.JSONField("passaggi", default=list)
    counts = models.JSONField("record ripristinati", default=dict, blank=True)
    duration_seconds = models.PositiveIntegerField("durata (s)", default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")

    class Meta:
        verbose_name = "prova di ripristino"
        verbose_name_plural = "prove di ripristino"
        ordering = ["-created_at"]
        default_permissions = ("view",)

    def __str__(self):
        return f"Prova di ripristino {self.created_at:%d/%m/%Y} – {self.get_result_display()}"
