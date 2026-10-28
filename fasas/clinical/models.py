import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import ShiftRecordModel, TimeStampedModel


class Therapy(TimeStampedModel):
    """Prescrizione: farmaco, dose, orari, via di somministrazione, medico prescrittore."""

    class Route(models.TextChoices):
        ORAL = "oral", "Orale"
        SUBLINGUAL = "sublingual", "Sublinguale"
        BUCCAL = "buccal", "Buccale / oromucosale"
        RECTAL = "rectal", "Rettale"
        IM = "im", "Intramuscolare"
        SC = "sc", "Sottocutanea"
        IV = "iv", "Endovenosa"
        TOPICAL = "topical", "Topica / cutanea"
        TRANSDERMAL = "transdermal", "Transdermica"
        INHALATION = "inhalation", "Inalatoria"
        OPHTHALMIC = "ophthalmic", "Oftalmica"
        NASAL = "nasal", "Nasale"
        PEG = "peg", "Via PEG / sondino"
        OTHER = "other", "Altro"

    class Status(models.TextChoices):
        ACTIVE = "active", "Attiva"
        SUSPENDED = "suspended", "Sospesa"
        ENDED = "ended", "Terminata"

    guest = models.ForeignKey("guests.Guest", verbose_name="ospite", on_delete=models.PROTECT, related_name="therapies")
    drug = models.ForeignKey("pharmacy.Drug", verbose_name="farmaco", on_delete=models.PROTECT, related_name="therapies")
    dose = models.DecimalField("dose", max_digits=10, decimal_places=3)
    dose_unit = models.CharField("unità dose", max_length=30, default="cp", help_text="cp, mg, ml, gtt, UI...")
    stock_units_per_dose = models.DecimalField(
        "unità scaricate dal magazzino per dose", max_digits=8, decimal_places=2, default=Decimal("1"),
        help_text="Es. 0.5 per mezza compressa, 20 per 20 gocce se il magazzino è in gocce",
    )
    route = models.CharField("modalità di somministrazione", max_length=20, choices=Route.choices, default=Route.ORAL)
    schedule_times = models.JSONField(
        "orari", default=list, blank=True, help_text="Orari HH:MM; vuoto per i farmaci al bisogno (SOS)"
    )
    every_n_days = models.PositiveSmallIntegerField(
        "frequenza (ogni N giorni)", default=1, help_text="1 = tutti i giorni, 7 = settimanale"
    )
    start_date = models.DateField("inizio", default=timezone.localdate)
    end_date = models.DateField("fine", null=True, blank=True)
    instructions = models.TextField("istruzioni (es. a stomaco pieno, frantumabile)", blank=True)

    is_sos = models.BooleanField("farmaco al bisogno (SOS)", default=False)
    sos_indication = models.CharField(
        "indicazione SOS", max_length=255, blank=True, help_text="Es. crisi epilettica > 3 minuti, TC > 38°C, agitazione"
    )
    sos_max_daily = models.PositiveSmallIntegerField("SOS: massimo somministrazioni in 24h", null=True, blank=True)
    sos_min_interval_hours = models.PositiveSmallIntegerField("SOS: intervallo minimo (ore)", null=True, blank=True)
    sos_requires_validation = models.BooleanField(
        "SOS: richiede validazione di medico o coordinatore", default=True
    )

    prescriber = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="medico prescrittore (utente)", on_delete=models.PROTECT,
        null=True, blank=True, related_name="prescriptions",
    )
    prescriber_name = models.CharField(
        "medico prescrittore", max_length=150, blank=True, help_text="Se esterno (MMG, specialista)"
    )
    prescription_date = models.DateField("data prescrizione", default=timezone.localdate)
    prescription_document = models.ForeignKey(
        "documents.Document", verbose_name="prescrizione allegata", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    status = models.CharField("stato", max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    status_reason = models.CharField("motivo sospensione/termine", max_length=255, blank=True)
    conflict_acknowledged = models.TextField(
        "avvisi confermati all'inserimento", blank=True, editable=False,
        help_text="Avvisi di duplicato/interazione/allergia mostrati e confermati dal prescrittore",
    )

    class Meta:
        verbose_name = "terapia"
        verbose_name_plural = "terapie"
        ordering = ["is_sos", "drug__name"]
        permissions = [("validate_sos", "Può validare le somministrazioni di farmaci SOS")]

    def __str__(self):
        return f"{self.drug} {self.dose_display}{' (SOS)' if self.is_sos else ''}"

    def get_absolute_url(self):
        return reverse("clinical:therapy_detail", args=[self.pk])

    @property
    def dose_display(self):
        return f"{self.dose.normalize():f} {self.dose_unit}"

    @property
    def prescriber_display(self):
        return str(self.prescriber) if self.prescriber else self.prescriber_name

    def parsed_times(self):
        times = []
        for value in self.schedule_times or []:
            try:
                times.append(datetime.datetime.strptime(value, "%H:%M").time())
            except (TypeError, ValueError):
                continue
        return sorted(times)

    def is_active_on(self, day):
        if self.status != self.Status.ACTIVE or self.is_sos:
            return False
        if day < self.start_date or (self.end_date and day > self.end_date):
            return False
        return (day - self.start_date).days % max(self.every_n_days, 1) == 0

    def clean(self):
        if not self.is_sos and not self.parsed_times():
            raise ValidationError({"schedule_times": "Indicare almeno un orario per una terapia programmata."})
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La data di fine precede l'inizio."})
        if not self.prescriber_id and not self.prescriber_name:
            raise ValidationError({"prescriber_name": "Indicare il medico prescrittore."})


class TherapyAdministration(ShiftRecordModel):
    class Status(models.TextChoices):
        GIVEN = "given", "Somministrato"
        REFUSED = "refused", "Rifiutato dall'ospite"
        NOT_GIVEN = "not_given", "Non somministrato"
        HELD = "held", "Sospeso su indicazione"

    class Validation(models.TextChoices):
        NOT_REQUIRED = "not_required", "Non richiesta"
        PENDING = "pending", "In attesa di validazione"
        VALIDATED = "validated", "Validata"
        REJECTED = "rejected", "Non validata"

    therapy = models.ForeignKey(Therapy, verbose_name="terapia", on_delete=models.PROTECT, related_name="administrations")
    scheduled_date = models.DateField("data programmata", null=True, blank=True)
    scheduled_time = models.TimeField("orario programmato", null=True, blank=True)
    status = models.CharField("esito", max_length=20, choices=Status.choices, default=Status.GIVEN)
    dose_given = models.CharField("dose somministrata", max_length=60, blank=True)
    notes = models.TextField("note", blank=True)

    is_sos = models.BooleanField("SOS", default=False)
    sos_reason = models.TextField("motivo della somministrazione SOS", blank=True)
    validation_status = models.CharField(
        "validazione", max_length=20, choices=Validation.choices, default=Validation.NOT_REQUIRED
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    validation_notes = models.TextField("note validazione", blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "somministrazione"
        verbose_name_plural = "somministrazioni"
        constraints = [
            models.UniqueConstraint(
                fields=["therapy", "scheduled_date", "scheduled_time"],
                condition=models.Q(voided_at__isnull=True, scheduled_time__isnull=False),
                name="unique_scheduled_administration",
            )
        ]

    def __str__(self):
        when = timezone.localtime(self.occurred_at)
        return f"{self.therapy.drug} – {self.guest} – {when:%d/%m %H:%M} ({self.get_status_display()})"


class ParameterType(models.Model):
    class Kind(models.TextChoices):
        SINGLE = "single", "Valore singolo"
        BLOOD_PRESSURE = "bp", "Pressione (sistolica/diastolica)"

    code = models.SlugField("codice", max_length=30, unique=True)
    name = models.CharField("nome", max_length=80)
    unit = models.CharField("unità", max_length=20)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.SINGLE)
    min_normal = models.DecimalField("valore minimo normale", max_digits=8, decimal_places=2, null=True, blank=True)
    max_normal = models.DecimalField("valore massimo normale", max_digits=8, decimal_places=2, null=True, blank=True)
    min_normal_2 = models.DecimalField("minimo normale (diastolica)", max_digits=8, decimal_places=2, null=True, blank=True)
    max_normal_2 = models.DecimalField("massimo normale (diastolica)", max_digits=8, decimal_places=2, null=True, blank=True)
    decimals = models.PositiveSmallIntegerField("decimali", default=1)
    show_chart = models.BooleanField("mostra grafico", default=True)
    active = models.BooleanField("attivo", default=True)
    order = models.PositiveSmallIntegerField("ordine", default=0)

    class Meta:
        verbose_name = "tipo di parametro"
        verbose_name_plural = "tipi di parametro"
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} ({self.unit})"


class ParameterReading(ShiftRecordModel):
    parameter_type = models.ForeignKey(
        ParameterType, verbose_name="parametro", on_delete=models.PROTECT, related_name="readings"
    )
    value = models.DecimalField("valore", max_digits=8, decimal_places=2)
    value_2 = models.DecimalField("valore 2 (diastolica)", max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "rilevazione parametro"
        verbose_name_plural = "parametri sanitari"

    def __str__(self):
        return f"{self.parameter_type.name}: {self.display_value} – {self.guest}"

    @property
    def display_value(self):
        fmt = f"{{:.{self.parameter_type.decimals}f}}"
        if self.parameter_type.kind == ParameterType.Kind.BLOOD_PRESSURE and self.value_2 is not None:
            return f"{self.value:.0f}/{self.value_2:.0f} {self.parameter_type.unit}"
        return f"{fmt.format(self.value)} {self.parameter_type.unit}"

    @property
    def out_of_range(self):
        t = self.parameter_type
        checks = [(self.value, t.min_normal, t.max_normal), (self.value_2, t.min_normal_2, t.max_normal_2)]
        for value, low, high in checks:
            if value is None:
                continue
            if (low is not None and value < low) or (high is not None and value > high):
                return True
        return False


class ClinicalEvent(ShiftRecordModel):
    class EventType(models.TextChoices):
        FALL = "fall", "Caduta"
        SEIZURE = "seizure", "Crisi epilettica"
        AGITATION = "agitation", "Agitazione / crisi comportamentale"
        INTERVENTION = "intervention", "Intervento sanitario"
        INCIDENT = "incident", "Incidente / infortunio"
        EMERGENCY = "emergency", "Emergenza sanitaria"
        SELF_HARM = "self_harm", "Autolesionismo"
        AGGRESSION = "aggression", "Aggressione"
        ELOPEMENT = "elopement", "Allontanamento"
        OTHER = "other", "Altro"

    class Severity(models.TextChoices):
        LOW = "low", "Lieve"
        MEDIUM = "medium", "Moderata"
        HIGH = "high", "Grave"
        CRITICAL = "critical", "Critica"

    event_type = models.CharField("tipo evento", max_length=20, choices=EventType.choices)
    severity = models.CharField("gravità", max_length=10, choices=Severity.choices, default=Severity.LOW)
    duration_minutes = models.PositiveIntegerField("durata (minuti)", null=True, blank=True)
    location = models.CharField("luogo", max_length=120, blank=True)
    description = models.TextField("descrizione")
    actions_taken = models.TextField("interventi effettuati", blank=True)
    injuries = models.TextField("conseguenze / lesioni", blank=True)
    doctor_notified = models.BooleanField("medico avvisato", default=False)
    family_notified = models.BooleanField("familiari/tutore avvisati", default=False)
    emergency_services_called = models.BooleanField("chiamato 118/112", default=False)
    is_emergency = models.BooleanField("registrato in modalità emergenza", default=False, editable=False)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "evento sanitario"
        verbose_name_plural = "eventi sanitari"

    def __str__(self):
        when = timezone.localtime(self.occurred_at)
        return f"{self.get_event_type_display()} – {self.guest} – {when:%d/%m/%Y %H:%M}"


class Restraint(ShiftRecordModel):
    """Contenzione: sempre su prescrizione medica, motivata, a tempo e monitorata."""

    class RestraintType(models.TextChoices):
        BED_RAILS = "bed_rails", "Spondine al letto"
        BELT = "belt", "Cintura / corpetto"
        WRIST = "wrist", "Polsiere / cavigliere"
        CHAIR = "chair", "Tavolino / sistema di postura in carrozzina"
        PHARMACOLOGICAL = "pharmacological", "Contenzione farmacologica"
        ENVIRONMENTAL = "environmental", "Contenzione ambientale"
        OTHER = "other", "Altro"

    restraint_type = models.CharField("tipo contenzione", max_length=20, choices=RestraintType.choices)
    reason = models.TextField("motivo")
    alternatives_tried = models.TextField("alternative tentate", blank=True)
    ended_at = models.DateTimeField("fine", null=True, blank=True)
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="medico che autorizza (utente)", on_delete=models.PROTECT,
        null=True, blank=True, related_name="authorized_restraints",
    )
    authorizing_doctor_name = models.CharField("medico che autorizza", max_length=150, blank=True)
    authorization_date = models.DateField("data autorizzazione")
    authorization_document = models.ForeignKey(
        "documents.Document", verbose_name="autorizzazione allegata", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    responsible_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="operatore responsabile", on_delete=models.PROTECT,
        related_name="restraints_responsible",
    )
    monitoring_notes = models.TextField("monitoraggio (controlli effettuati)", blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "contenzione"
        verbose_name_plural = "contenzioni"

    def __str__(self):
        return f"{self.get_restraint_type_display()} – {self.guest}"

    @property
    def started_at(self):
        return self.occurred_at

    @property
    def duration(self):
        end = self.ended_at or timezone.now()
        return end - self.occurred_at

    @property
    def duration_display(self):
        minutes = int(self.duration.total_seconds() // 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"

    @property
    def authorizing_doctor_display(self):
        return str(self.authorized_by) if self.authorized_by else self.authorizing_doctor_name

    def clean(self):
        if self.ended_at and self.ended_at < self.occurred_at:
            raise ValidationError({"ended_at": "La fine precede l'inizio della contenzione."})
        if not self.authorized_by_id and not self.authorizing_doctor_name:
            raise ValidationError({"authorizing_doctor_name": "La contenzione richiede l'autorizzazione di un medico."})
