import datetime

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import Community, TimeStampedModel

fiscal_code_validator = RegexValidator(
    r"^[A-Z0-9]{16}$", "Il codice fiscale deve avere 16 caratteri alfanumerici."
)


class ClinicalTag(models.Model):
    """Tag clinici (diabetico, epilettico, disfagia, rischio caduta...): filtri, avvisi e notifiche."""

    name = models.CharField("nome", max_length=60, unique=True)
    color = models.CharField("colore", max_length=7, default="#2563eb", help_text="Esadecimale, es. #dc2626")
    description = models.TextField("descrizione", blank=True)
    alert_message = models.CharField(
        "avviso per gli operatori", max_length=255, blank=True,
        help_text="Mostrato sulla cartella e nel giro farmaci, es. «Controllare glicemia prima dei pasti»",
    )
    escalate_event_types = models.JSONField(
        "eventi da segnalare con priorità critica", default=list, blank=True,
        help_text="Codici evento (es. fall, seizure): se l'ospite ha il tag, l'evento genera una notifica critica",
    )
    order = models.PositiveIntegerField("ordine", default=0)

    class Meta:
        verbose_name = "tag clinico"
        verbose_name_plural = "tag clinici"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class GuestQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Guest.Status.ACTIVE)

    def archived(self):
        return self.filter(status=Guest.Status.ARCHIVED)


class Guest(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Presente"
        HOSPITALIZED = "hospitalized", "Ricoverato / assente temporaneamente"
        ARCHIVED = "archived", "Dimesso – cartella archiviata"

    class Sex(models.TextChoices):
        F = "F", "Femmina"
        M = "M", "Maschio"
        X = "X", "Non specificato"

    community = models.ForeignKey(Community, on_delete=models.PROTECT, related_name="guests")
    first_name = models.CharField("nome", max_length=100)
    last_name = models.CharField("cognome", max_length=100)
    sex = models.CharField("sesso", max_length=1, choices=Sex.choices, default=Sex.X)
    birth_date = models.DateField("data di nascita")
    birth_place = models.CharField("luogo di nascita", max_length=120, blank=True)
    fiscal_code = models.CharField("codice fiscale", max_length=16, unique=True, validators=[fiscal_code_validator])
    health_card_number = models.CharField("numero tessera sanitaria", max_length=30, blank=True)
    residence_address = models.CharField("residenza – indirizzo", max_length=255, blank=True)
    residence_city = models.CharField("residenza – comune", max_length=120, blank=True)
    residence_zip = models.CharField("CAP", max_length=10, blank=True)
    room = models.CharField("camera / posto letto", max_length=30, blank=True)

    general_practitioner = models.CharField("medico curante", max_length=150, blank=True)
    general_practitioner_phone = models.CharField("telefono medico curante", max_length=50, blank=True)
    general_practitioner_email = models.EmailField("email medico curante", blank=True)
    referring_service = models.CharField("servizio inviante / ente pagante", max_length=200, blank=True)

    disability_description = models.TextField("disabilità", blank=True)
    disability_certifications = models.CharField(
        "certificazioni (L.104, invalidità %)", max_length=255, blank=True
    )
    diet = models.CharField("dieta", max_length=255, blank=True)
    diet_texture = models.CharField(
        "consistenza alimenti", max_length=100, blank=True, help_text="Es. normale, tritata, frullata, acqua gelificata"
    )
    clinical_notes = models.TextField("note cliniche generali", blank=True)
    tags = models.ManyToManyField(ClinicalTag, verbose_name="tag clinici", blank=True, related_name="guests")

    admission_date = models.DateField("data ingresso", default=datetime.date.today)
    status = models.CharField("stato", max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    discharge_date = models.DateField("data dimissione", null=True, blank=True)
    discharge_reason = models.TextField("motivo dimissione", blank=True)
    discharge_destination = models.CharField("destinazione", max_length=255, blank=True)
    archived_at = models.DateTimeField("archiviata il", null=True, blank=True, editable=False)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+", editable=False
    )
    retention_until = models.DateField("conservazione fino al", null=True, blank=True, editable=False)

    objects = GuestQuerySet.as_manager()

    class Meta:
        verbose_name = "ospite"
        verbose_name_plural = "ospiti"
        ordering = ["last_name", "first_name"]
        permissions = [
            ("archive_guest", "Può dimettere e archiviare un ospite"),
            ("export_guest", "Può esportare la cartella completa"),
        ]

    def __str__(self):
        return f"{self.last_name} {self.first_name}"

    def get_absolute_url(self):
        return reverse("guests:detail", args=[self.pk])

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_archived(self):
        return self.status == self.Status.ARCHIVED

    @property
    def age(self):
        today = timezone.localdate()
        b = self.birth_date
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))

    @property
    def initials(self):
        return f"{self.first_name[:1]}{self.last_name[:1]}".upper()

    def save(self, *args, **kwargs):
        self.fiscal_code = (self.fiscal_code or "").upper().strip()
        super().save(*args, **kwargs)


class GuestContact(TimeStampedModel):
    class Kind(models.TextChoices):
        FAMILY = "family", "Familiare"
        GUARDIAN = "guardian", "Tutore legale"
        SUPPORT_ADMIN = "support_admin", "Amministratore di sostegno"
        CURATOR = "curator", "Curatore"
        SOCIAL_WORKER = "social_worker", "Assistente sociale"
        OTHER = "other", "Altro"

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="contacts")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.FAMILY)
    name = models.CharField("nome e cognome", max_length=150)
    relationship = models.CharField("relazione / parentela", max_length=100, blank=True)
    phone = models.CharField("telefono", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    address = models.CharField("indirizzo", max_length=255, blank=True)
    legal_reference = models.CharField(
        "riferimento decreto di nomina", max_length=150, blank=True, help_text="Per tutori e amministratori di sostegno"
    )
    is_emergency_contact = models.BooleanField("da contattare in emergenza", default=False)
    can_receive_health_info = models.BooleanField("autorizzato a ricevere informazioni sanitarie", default=False)
    notes = models.TextField("note", blank=True)

    class Meta:
        verbose_name = "contatto"
        verbose_name_plural = "contatti"
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    @property
    def is_legal_guardian(self):
        return self.kind in {self.Kind.GUARDIAN, self.Kind.SUPPORT_ADMIN, self.Kind.CURATOR}


class Diagnosis(TimeStampedModel):
    class Kind(models.TextChoices):
        DIAGNOSIS = "diagnosis", "Diagnosi"
        PATHOLOGY = "pathology", "Patologia"

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="diagnoses")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.DIAGNOSIS)
    description = models.CharField("descrizione", max_length=255)
    icd_code = models.CharField("codice ICD", max_length=20, blank=True)
    diagnosed_on = models.DateField("data", null=True, blank=True)
    is_primary = models.BooleanField("principale", default=False)
    active = models.BooleanField("attiva", default=True)
    notes = models.TextField("note", blank=True)

    class Meta:
        verbose_name = "diagnosi / patologia"
        verbose_name_plural = "diagnosi e patologie"
        ordering = ["-is_primary", "-active", "description"]

    def __str__(self):
        return self.description


class Allergy(TimeStampedModel):
    class Kind(models.TextChoices):
        ALLERGY = "allergy", "Allergia"
        INTOLERANCE = "intolerance", "Intolleranza"

    class Category(models.TextChoices):
        DRUG = "drug", "Farmaco"
        FOOD = "food", "Alimento"
        ENVIRONMENT = "environment", "Ambientale"
        OTHER = "other", "Altro"

    class Severity(models.TextChoices):
        MILD = "mild", "Lieve"
        MODERATE = "moderate", "Moderata"
        SEVERE = "severe", "Grave / anafilassi"

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="allergies")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.ALLERGY)
    category = models.CharField("categoria", max_length=20, choices=Category.choices, default=Category.DRUG)
    substance = models.CharField(
        "sostanza", max_length=150, help_text="Per i farmaci indicare il principio attivo: viene usato per gli avvisi"
    )
    reaction = models.CharField("reazione", max_length=255, blank=True)
    severity = models.CharField("gravità", max_length=20, choices=Severity.choices, default=Severity.MODERATE)
    notes = models.TextField("note", blank=True)

    class Meta:
        verbose_name = "allergia / intolleranza"
        verbose_name_plural = "allergie e intolleranze"
        ordering = ["-severity", "substance"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.substance}"


class AdmissionEvent(TimeStampedModel):
    """Movimenti dell'ospite (ingresso, ricoveri, rientri, dimissione) per lo storico."""

    class Kind(models.TextChoices):
        ADMISSION = "admission", "Ingresso"
        HOSPITALIZATION = "hospitalization", "Ricovero ospedaliero"
        ABSENCE = "absence", "Assenza temporanea (rientro in famiglia)"
        RETURN = "return", "Rientro in struttura"
        DISCHARGE = "discharge", "Dimissione"

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="admission_events")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    date = models.DateField("data", default=datetime.date.today)
    notes = models.TextField("note", blank=True)

    class Meta:
        verbose_name = "movimento ospite"
        verbose_name_plural = "movimenti ospite"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.date:%d/%m/%Y}"
