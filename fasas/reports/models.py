from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ReportType(models.TextChoices):
    DAILY_REGISTER = "daily_register", "Registro giornaliero"
    MEDICATIONS = "medications", "Farmaci somministrati"
    EVENTS = "events", "Eventi sanitari e contenzioni"
    PARAMETERS = "parameters", "Parametri sanitari"
    PROTOCOLS = "protocols", "Protocolli attivati"


class ReportFormat(models.TextChoices):
    PDF = "pdf", "PDF"
    XLSX = "xlsx", "Excel"


BOTH_FORMATS = "both"
FORMAT_CHOICES = ReportFormat.choices + [(BOTH_FORMATS, "PDF ed Excel")]


class ReportTemplate(models.Model):
    """
    Modello di report salvato: più sezioni nell'ordine scelto, con le sole colonne scelte per ciascuna.
    sections = [{"type": "medications", "columns": ["Data/ora", "Ospite", "Farmaco"]}, ...]
    """

    name = models.CharField("nome", max_length=150, unique=True)
    description = models.CharField("descrizione", max_length=255, blank=True)
    sections = models.JSONField("sezioni", default=list)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "modello di report"
        verbose_name_plural = "modelli di report"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def sections_display(self):
        labels = dict(ReportType.choices)
        return " · ".join(f"{labels.get(s['type'], s['type'])} ({len(s.get('columns') or [])} colonne)"
                          for s in self.sections)

    sections_display.short_description = "sezioni"


class ReportSchedule(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Giornaliera (giorno precedente)"
        WEEKLY = "weekly", "Settimanale (settimana precedente)"
        MONTHLY = "monthly", "Mensile (mese precedente)"
        INTERVAL = "interval", "Ogni N giorni (gli N giorni precedenti)"

    name = models.CharField("nome", max_length=150)
    report_type = models.CharField("contenuto", max_length=30, choices=ReportType.choices, blank=True,
                                   help_text="Oppure scegliere un modello di report qui sotto.")
    template = models.ForeignKey(ReportTemplate, verbose_name="modello di report", on_delete=models.PROTECT,
                                 null=True, blank=True)
    format = models.CharField("formato", max_length=5, choices=FORMAT_CHOICES, default=ReportFormat.PDF)
    frequency = models.CharField("frequenza", max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    interval_days = models.PositiveSmallIntegerField(
        "ogni quanti giorni", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(366)],
        help_text="Solo per la frequenza «ogni N giorni».")
    guest = models.ForeignKey("guests.Guest", verbose_name="solo per l'ospite", on_delete=models.CASCADE,
                              null=True, blank=True, help_text="Vuoto = tutti gli ospiti")
    retention_years = models.PositiveSmallIntegerField(
        "conservazione (anni)", default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    active = models.BooleanField("attiva", default=True)
    last_run_at = models.DateTimeField("ultima esecuzione", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "report programmato"
        verbose_name_plural = "report programmati"
        ordering = ["name"]

    def __str__(self):
        return self.name


class GeneratedReport(models.Model):
    schedule = models.ForeignKey(ReportSchedule, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="reports")
    report_type = models.CharField("contenuto", max_length=30, choices=ReportType.choices + [
        ("guest_folder", "Cartella completa ospite"), ("custom", "Report da modello"),
    ])
    format = models.CharField("formato", max_length=5, choices=ReportFormat.choices)
    title = models.CharField("titolo", max_length=255)
    period_start = models.DateField("dal", null=True, blank=True)
    period_end = models.DateField("al", null=True, blank=True)
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    storage_name = models.CharField(max_length=255, editable=False)
    filename = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    generated_at = models.DateTimeField(default=timezone.now, db_index=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+")
    expires_on = models.DateField("conservato fino al", db_index=True)

    class Meta:
        verbose_name = "report generato"
        verbose_name_plural = "report generati"
        ordering = ["-generated_at"]
        permissions = [("view_quality_indicators", "Può vedere gli indicatori di qualità nel tempo")]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "period_start", "period_end", "format"], condition=models.Q(schedule__isnull=False),
                name="unique_schedule_period_format",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def content_type(self):
        if self.format == ReportFormat.PDF:
            return "application/pdf"
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
