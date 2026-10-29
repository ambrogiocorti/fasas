from django.conf import settings
from django.db import models
from django.utils import timezone


class ImportBatch(models.Model):
    """
    Un'importazione dal FASAS cartaceo. Il file caricato resta cifrato solo tra l'anteprima e la
    conferma, poi viene cancellato: dei dati importati resta traccia nell'audit log (origine «import»).
    """

    class Kind(models.TextChoices):
        WORKBOOK = "workbook", "Foglio Excel"
        DOCUMENTS = "documents", "Documenti scansionati"

    class Status(models.TextChoices):
        PREVIEW = "preview", "In anteprima"
        COMPLETED = "completed", "Importato"
        CANCELLED = "cancelled", "Annullato"

    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    status = models.CharField("stato", max_length=20, choices=Status.choices, default=Status.PREVIEW)
    filename = models.CharField("file", max_length=255)
    sha256 = models.CharField("impronta SHA-256", max_length=64, blank=True)
    payload = models.JSONField("file in attesa", default=list, blank=True, editable=False)
    summary = models.JSONField("riepilogo", default=dict, blank=True)
    created_at = models.DateTimeField("caricato il", default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    completed_at = models.DateTimeField("completato il", null=True, blank=True)

    class Meta:
        verbose_name = "importazione"
        verbose_name_plural = "importazioni"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.filename} ({self.created_at:%d/%m/%Y})"
