"""
Pianificazione mensile dei turni del personale: calendario per operatore, ferie e permessi con approvazione,
cambi turno e sostituzioni, controllo della copertura minima e dei riposi.
Il «registro turni» (daily.ShiftAssignment) resta la registrazione di chi ha effettivamente preso servizio.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from fasas.core.models import Community


class Code(models.TextChoices):
    MORNING = "M", "Mattina"
    AFTERNOON = "P", "Pomeriggio"
    NIGHT = "N", "Notte"
    REST = "R", "Riposo"
    HOLIDAY = "F", "Ferie"
    PERMIT = "PE", "Permesso"
    SICK = "MA", "Malattia"
    TRAINING = "FO", "Formazione"


SHIFT_CODES = (Code.MORNING, Code.AFTERNOON, Code.NIGHT)
WORK_CODES = (*SHIFT_CODES, Code.TRAINING)
ABSENCE_CODES = (Code.HOLIDAY, Code.PERMIT, Code.SICK)


class RotaSettings(models.Model):
    community = models.OneToOneField(Community, on_delete=models.CASCADE, related_name="rota_settings")
    min_morning = models.PositiveSmallIntegerField("minimo operatori di mattina", default=2)
    min_afternoon = models.PositiveSmallIntegerField("minimo operatori di pomeriggio", default=2)
    min_night = models.PositiveSmallIntegerField("minimo operatori di notte", default=1)
    min_rest_hours = models.PositiveSmallIntegerField("riposo minimo tra due turni (ore)", default=11)
    max_consecutive_days = models.PositiveSmallIntegerField("massimo giorni lavorativi consecutivi", default=6)
    training_hours = models.DecimalField("ore conteggiate per una giornata di formazione", max_digits=4,
                                         decimal_places=1, default=Decimal("7"))

    class Meta:
        verbose_name = "regole dei turni"
        verbose_name_plural = "regole dei turni"

    def __str__(self):
        return f"Regole turni {self.community}"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(community=Community.default())
        return obj

    def minimum(self, code):
        return {Code.MORNING: self.min_morning, Code.AFTERNOON: self.min_afternoon, Code.NIGHT: self.min_night}[code]


class StaffProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    in_rota = models.BooleanField("compare nel calendario dei turni", default=True)
    weekly_hours = models.DecimalField("ore settimanali da contratto", max_digits=4, decimal_places=1,
                                       default=Decimal("36"))
    can_lead = models.BooleanField("può essere responsabile di turno", default=False)
    no_nights = models.BooleanField("esonerato dai turni di notte", default=False)
    order = models.PositiveSmallIntegerField("ordine nel calendario", default=0)

    class Meta:
        verbose_name = "profilo turni"
        verbose_name_plural = "profili turni"
        ordering = ["order", "user__last_name"]

    def __str__(self):
        return f"Profilo turni {self.user}"


class RotaMonth(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "In preparazione"
        PUBLISHED = "published", "Pubblicato"

    month = models.DateField("mese", unique=True)
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField("pubblicato il", null=True, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+")
    notes = models.TextField("note per il personale", blank=True)

    class Meta:
        verbose_name = "calendario turni del mese"
        verbose_name_plural = "calendari turni"
        ordering = ["-month"]
        permissions = [("publish_rota", "Può pubblicare il calendario dei turni")]

    def __str__(self):
        return f"Turni {self.month:%m/%Y}"

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED


class RotaEntry(models.Model):
    date = models.DateField("giorno", db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rota_entries")
    code = models.CharField("turno o assenza", max_length=2, choices=Code.choices)
    is_lead = models.BooleanField("responsabile di turno", default=False)
    note = models.CharField("nota", max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "turno pianificato"
        verbose_name_plural = "turni pianificati"
        ordering = ["date", "user__last_name"]
        constraints = [models.UniqueConstraint(fields=["date", "user"], name="unique_rota_entry")]

    def __str__(self):
        return f"{self.date:%d/%m/%Y} {self.user}: {self.get_code_display()}"


class RequestStatus(models.TextChoices):
    PENDING = "pending", "In attesa"
    ACCEPTED = "accepted", "Accettata dal collega"
    APPROVED = "approved", "Approvata"
    REJECTED = "rejected", "Respinta"
    CANCELLED = "cancelled", "Ritirata"


class LeaveRequest(models.Model):
    class Kind(models.TextChoices):
        HOLIDAY = "F", "Ferie"
        PERMIT = "PE", "Permesso"
        TRAINING = "FO", "Formazione"
        SICK = "MA", "Malattia"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="leave_requests")
    kind = models.CharField("tipo", max_length=2, choices=Kind.choices, default=Kind.HOLIDAY)
    start = models.DateField("dal")
    end = models.DateField("al")
    note = models.CharField("nota", max_length=255, blank=True)
    status = models.CharField("stato", max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField("nota della decisione", max_length=255, blank=True)

    class Meta:
        verbose_name = "richiesta di ferie o permesso"
        verbose_name_plural = "richieste di ferie e permessi"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.user} {self.start:%d/%m}–{self.end:%d/%m}"

    @property
    def days(self):
        return (self.end - self.start).days + 1


class ShiftChange(models.Model):
    """Cambio turno tra due colleghi nello stesso giorno, o sostituzione di un turno da parte di un collega."""

    class Kind(models.TextChoices):
        SWAP = "swap", "Cambio turno"
        COVER = "cover", "Sostituzione"

    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    date = models.DateField("giorno")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shift_changes")
    colleague = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    requester_code = models.CharField("turno di chi chiede", max_length=2, choices=Code.choices)
    colleague_code = models.CharField("turno del collega", max_length=2, choices=Code.choices)
    requester_new_code = models.CharField("nuovo codice di chi chiede (sostituzione)", max_length=2,
                                          choices=Code.choices, default=Code.REST)
    note = models.CharField("motivo", max_length=255, blank=True)
    status = models.CharField("stato", max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField("nota della decisione", max_length=255, blank=True)

    class Meta:
        verbose_name = "cambio turno / sostituzione"
        verbose_name_plural = "cambi turno e sostituzioni"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.date:%d/%m} {self.requester} ↔ {self.colleague}"


class CredentialType(models.Model):
    """Corso, idoneità o visita che il personale deve avere in regola (es. BLSD, antincendio, idoneità alla mansione)."""

    class Category(models.TextChoices):
        TRAINING = "training", "Corso di formazione"
        FITNESS = "fitness", "Idoneità e visite del medico competente"
        OTHER = "other", "Altro (titolo professionale, iscrizione…)"

    name = models.CharField("nome", max_length=120, unique=True)
    category = models.CharField("tipo", max_length=10, choices=Category.choices, default=Category.TRAINING)
    validity_months = models.PositiveSmallIntegerField(
        "validità (mesi)", null=True, blank=True,
        help_text="Vuoto = senza scadenza fissa (si indica la data di scadenza a ogni registrazione). "
                  "Periodicità proposte da verificare con l'RSPP e il medico competente.")
    warn_days = models.PositiveSmallIntegerField("avviso (giorni prima)", default=60)
    roles = models.JSONField("obbligatorio per i ruoli", default=list, blank=True,
                             help_text="Ruoli per cui manca se non registrato. Vuoto = solo per chi è designato.")
    reference = models.CharField("riferimento", max_length=200, blank=True)
    active = models.BooleanField("in uso", default=True)
    order = models.PositiveSmallIntegerField("ordine", default=0)

    class Meta:
        verbose_name = "tipo di scadenza del personale"
        verbose_name_plural = "tipi di scadenza del personale"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def required_for(self, user):
        return user.role in (self.roles or [])


class StaffCredential(models.Model):
    """Attestato di un corso o giudizio di idoneità di un dipendente. La registrazione più recente è quella valida."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="dipendente", on_delete=models.PROTECT,
                             related_name="credentials")
    type = models.ForeignKey(CredentialType, verbose_name="tipo", on_delete=models.PROTECT, related_name="credentials")
    obtained_on = models.DateField("conseguito / visita del")
    expires_on = models.DateField("scadenza", null=True, blank=True,
                                  help_text="Se vuota si calcola dalla validità del tipo.")
    provider = models.CharField("ente o medico", max_length=120, blank=True)
    notes = models.CharField("note", max_length=255, blank=True,
                             help_text="Non indicare diagnosi né dati sanitari: basta l'esito consegnato al datore di lavoro.")
    certificate_storage = models.CharField(max_length=255, blank=True, editable=False)
    certificate_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    certificate_type = models.CharField(max_length=60, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", editable=False)

    class Meta:
        verbose_name = "scadenza del personale"
        verbose_name_plural = "scadenze del personale"
        ordering = ["-obtained_on", "-created_at"]

    def __str__(self):
        return f"{self.type} – {self.user}"
