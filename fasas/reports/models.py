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


class ReportSchedule(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Giornaliera (giorno precedente)"
        WEEKLY = "weekly", "Settimanale (settimana precedente)"
        MONTHLY = "monthly", "Mensile (mese precedente)"

    name = models.CharField("nome", max_length=150)
    report_type = models.CharField("contenuto", max_length=30, choices=ReportType.choices)
    format = models.CharField("formato", max_length=5, choices=ReportFormat.choices, default=ReportFormat.PDF)
    frequency = models.CharField("frequenza", max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
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
        ("guest_folder", "Cartella completa ospite"),
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
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "period_start", "period_end"], condition=models.Q(schedule__isnull=False),
                name="unique_schedule_period",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def content_type(self):
        if self.format == ReportFormat.PDF:
            return "application/pdf"
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
