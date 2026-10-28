import datetime

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .shifts import Shift, resolve_shift


class Community(models.Model):
    """La struttura che usa il sistema. Oggi è una sola: il modello esiste per la futura multi-comunità."""

    name = models.CharField("nome", max_length=200)
    code = models.SlugField("codice", max_length=50, unique=True)
    address = models.CharField("indirizzo", max_length=255, blank=True)
    phone = models.CharField("telefono", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    asl_code = models.CharField("codice struttura ASL/ATS", max_length=50, blank=True)
    active = models.BooleanField("attiva", default=True)

    class Meta:
        verbose_name = "comunità"
        verbose_name_plural = "comunità"

    def __str__(self):
        return self.name

    @classmethod
    def default(cls):
        community = cls.objects.filter(active=True).order_by("pk").first()
        if community is None:
            community = cls.objects.create(name="Comunità", code="comunita")
        return community


class SystemConfig(models.Model):
    class EvacuationMode(models.TextChoices):
        DAILY = "A", "Modalità A – registrazione giornaliera SI/NO"
        ON_EVENT = "B", "Modalità B – registrazione solo quando avviene"

    class EditLockPolicy(models.TextChoices):
        WITHIN_WINDOW = "window", "Modificabile solo entro la finestra (poi bloccato)"
        AFTER_WINDOW_REASON = "reason", "Dopo la finestra modificabile con motivazione"
        AFTER_WINDOW_COORDINATOR = "coordinator", "Dopo la finestra modificabile solo dal coordinatore"

    community = models.OneToOneField(Community, on_delete=models.CASCADE, related_name="config")

    evacuation_mode = models.CharField(
        "modalità evacuazione", max_length=1, choices=EvacuationMode.choices, default=EvacuationMode.DAILY
    )
    edit_lock_policy = models.CharField(
        "blocco modifiche dati sanitari",
        max_length=20,
        choices=EditLockPolicy.choices,
        default=EditLockPolicy.AFTER_WINDOW_REASON,
    )
    edit_window_hours = models.PositiveIntegerField(
        "finestra di modifica libera (ore)", default=24, validators=[MinValueValidator(1), MaxValueValidator(168)]
    )

    morning_start = models.TimeField("inizio turno mattina", default=datetime.time(7, 0))
    afternoon_start = models.TimeField("inizio turno pomeriggio", default=datetime.time(14, 0))
    night_start = models.TimeField("inizio turno notte", default=datetime.time(21, 0))
    auto_close_shifts = models.BooleanField("chiusura automatica dei turni", default=True)
    auto_close_grace_minutes = models.PositiveIntegerField(
        "minuti di tolleranza dopo fine turno prima della chiusura", default=120
    )
    allow_admin_reopen = models.BooleanField(
        "consenti all'amministratore la riapertura straordinaria di un turno (con motivazione)", default=False
    )

    max_upload_mb = models.PositiveIntegerField(
        "dimensione massima file (MB)", default=20, validators=[MinValueValidator(1), MaxValueValidator(500)]
    )
    allowed_upload_extensions = models.CharField(
        "estensioni ammesse", max_length=255, default="pdf,jpg,jpeg,png,tif,tiff,doc,docx,odt,xls,xlsx,txt,p7m"
    )

    report_retention_years = models.PositiveIntegerField(
        "conservazione report (anni)", default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    archive_retention_years = models.PositiveIntegerField(
        "conservazione cartelle archiviate (anni)", default=10, validators=[MinValueValidator(1)]
    )
    backup_retention_days = models.PositiveIntegerField("conservazione backup (giorni)", default=30)
    session_timeout_minutes = models.PositiveIntegerField(
        "disconnessione per inattività (minuti)", default=30, validators=[MinValueValidator(5)]
    )
    stock_expiry_warning_days = models.PositiveIntegerField("avviso scadenza farmaci (giorni prima)", default=30)
    pai_review_warning_days = models.PositiveIntegerField("avviso revisione PAI (giorni prima)", default=15)
    night_theme_auto = models.BooleanField(
        "tema scuro automatico durante il turno di notte", default=True
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configurazione di sistema"
        verbose_name_plural = "configurazione di sistema"
        permissions = [("edit_after_window", "Può modificare dati sanitari oltre la finestra di modifica")]

    def __str__(self):
        return f"Configurazione {self.community}"

    @classmethod
    def get(cls):
        community = Community.default()
        config, _ = cls.objects.select_related("community").get_or_create(community=community)
        return config

    @property
    def extensions(self):
        return {ext.strip().lower().lstrip(".") for ext in self.allowed_upload_extensions.split(",") if ext.strip()}


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("creato il", default=timezone.now, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creato da",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    updated_at = models.DateTimeField("modificato il", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="modificato da",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True


class ValidRecordQuerySet(models.QuerySet):
    def voided(self):
        return self.filter(voided_at__isnull=False)


class ValidRecordManager(models.Manager.from_queryset(ValidRecordQuerySet)):
    """Manager predefinito: esclude le registrazioni annullate (che restano nel database)."""

    def get_queryset(self):
        return super().get_queryset().filter(voided_at__isnull=True)


class ShiftRecordModel(TimeStampedModel):
    """
    Base per ogni registrazione clinico-assistenziale: è legata a un ospite, a un momento
    e al turno in cui è avvenuta. Le registrazioni non si cancellano mai: si annullano con
    motivazione, così l'audit e il FASAS restano completi.
    """

    guest = models.ForeignKey(
        "guests.Guest", verbose_name="ospite", on_delete=models.PROTECT, related_name="%(class)ss"
    )
    occurred_at = models.DateTimeField("data e ora", default=timezone.now)
    shift_date = models.DateField("giornata di turno", editable=False, db_index=True)
    shift = models.CharField("turno", max_length=1, choices=Shift.choices, editable=False)

    voided_at = models.DateTimeField("annullato il", null=True, blank=True, editable=False)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="annullato da",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    void_reason = models.TextField("motivo annullamento", blank=True, editable=False)

    objects = ValidRecordManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        ordering = ["-occurred_at"]

    def save(self, *args, **kwargs):
        self.shift_date, self.shift = resolve_shift(self.occurred_at)
        super().save(*args, **kwargs)

    @property
    def is_voided(self):
        return self.voided_at is not None

    def void(self, user, reason):
        from fasas.audit.context import audit_context

        self.voided_at = timezone.now()
        self.voided_by = user
        self.void_reason = reason
        with audit_context(reason=reason):
            self.save(update_fields=["voided_at", "voided_by", "void_reason", "updated_at"])
