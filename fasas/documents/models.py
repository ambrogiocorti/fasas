from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import TimeStampedModel


class Document(TimeStampedModel):
    class Category(models.TextChoices):
        IDENTITY = "identity", "Carta d'identità"
        HEALTH_CARD = "health_card", "Tessera sanitaria"
        CERTIFICATE = "certificate", "Certificato medico"
        CONSENT = "consent", "Consenso informato"
        MEDICAL_REPORT = "medical_report", "Relazione medica"
        LAB_REPORT = "lab_report", "Referto / esame"
        PRESCRIPTION = "prescription", "Prescrizione"
        PAI = "pai", "PAI"
        LEGAL = "legal", "Documento legale (nomina tutore, ADS)"
        RESTRAINT = "restraint", "Autorizzazione contenzione"
        OTHER = "other", "Altro"

    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="documents")
    category = models.CharField("categoria", max_length=30, choices=Category.choices, default=Category.OTHER)
    title = models.CharField("titolo", max_length=200)
    description = models.TextField("descrizione", blank=True)
    document_date = models.DateField("data del documento", null=True, blank=True)
    expires_on = models.DateField("scadenza", null=True, blank=True, help_text="Es. scadenza documento d'identità")

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documenti"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("documents:detail", args=[self.pk])

    @property
    def current_version(self):
        return self.versions.order_by("-number").first()


class DocumentVersion(models.Model):
    """Ogni caricamento è una nuova versione: le precedenti restano consultabili."""

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField("versione")
    storage_name = models.CharField(max_length=255, editable=False)
    original_name = models.CharField("nome file", max_length=255)
    content_type = models.CharField("tipo", max_length=100)
    size = models.PositiveBigIntegerField("dimensione (byte)")
    sha256 = models.CharField("impronta SHA-256", max_length=64)
    note = models.CharField("nota di versione", max_length=255, blank=True)
    uploaded_at = models.DateTimeField("caricato il", default=timezone.now)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    is_signed = models.BooleanField("firmato digitalmente", default=False)

    class Meta:
        verbose_name = "versione documento"
        verbose_name_plural = "versioni documento"
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="unique_document_version")]

    def __str__(self):
        return f"{self.document} v{self.number}"

    @property
    def guest(self):
        return self.document.guest

    @property
    def is_pdf(self):
        return self.content_type == "application/pdf" or self.original_name.lower().endswith(".pdf")
