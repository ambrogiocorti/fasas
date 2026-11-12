"""
Presenze degli ospiti per la rendicontazione e rette.

Le presenze di ogni giorno si ricavano dai movimenti dell'ospite (ingresso, ricovero, rientro in famiglia,
rientro, dimissione), con correzioni puntuali motivate. A fine mese il coordinatore (o l'ufficio
amministrativo) chiude il mese: le presenze vengono «fotografate» e non cambiano più, salvo riapertura
motivata. Dal mese chiuso si generano i prospetti di retta per ciascun ente pagante.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import Community, TimeStampedModel


class AttendanceStatus(models.TextChoices):
    PRESENT = "P", "Presente"
    HOSPITAL = "H", "Assente – ricovero ospedaliero"
    FAMILY = "F", "Assente – rientro in famiglia / programmata"
    ABSENT = "A", "Assente – altro motivo"
    NOT_IN_CARE = "-", "Non in carico"


ABSENCES = (AttendanceStatus.HOSPITAL, AttendanceStatus.FAMILY, AttendanceStatus.ABSENT)


class BillingSettings(models.Model):
    """Regole di conteggio e dati dell'ente gestore per i prospetti (una per comunità)."""

    community = models.OneToOneField(Community, on_delete=models.CASCADE, related_name="billing_settings")
    count_admission_day = models.BooleanField("il giorno di ingresso conta come presenza", default=True)
    count_discharge_day = models.BooleanField("il giorno di dimissione conta come presenza", default=False)
    departure_day_present = models.BooleanField(
        "il giorno di uscita (ricovero, rientro in famiglia) conta come presenza", default=True)
    return_day_present = models.BooleanField("il giorno di rientro in struttura conta come presenza", default=True)
    payee_name = models.CharField("ente gestore (intestazione dei prospetti)", max_length=200, blank=True)
    payee_tax_code = models.CharField("codice fiscale / partita IVA dell'ente", max_length=30, blank=True)
    payee_address = models.CharField("indirizzo dell'ente", max_length=255, blank=True)
    iban = models.CharField("IBAN per i pagamenti", max_length=34, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField("scadenza pagamento (giorni dall'emissione)", default=30)
    statement_notes = models.TextField("note in calce ai prospetti", blank=True,
                                       default="Il presente prospetto non costituisce fattura.")

    class Meta:
        verbose_name = "impostazioni presenze e rette"
        verbose_name_plural = "impostazioni presenze e rette"

    def __str__(self):
        return f"Impostazioni rette {self.community}"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(community=Community.default())
        return obj


class AttendanceCorrection(TimeStampedModel):
    """Correzione di un singolo giorno rispetto a quanto risulta dai movimenti (es. uscita non registrata)."""

    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="attendance_corrections")
    date = models.DateField("giorno")
    status = models.CharField("presenza", max_length=1, choices=AttendanceStatus.choices)
    reason = models.CharField("motivo della correzione", max_length=255)

    class Meta:
        verbose_name = "correzione presenze"
        verbose_name_plural = "correzioni presenze"
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["guest", "date"], name="unique_attendance_correction")]

    def __str__(self):
        return f"{self.guest} {self.date:%d/%m/%Y}: {self.get_status_display()}"


class AttendanceMonth(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Aperto"
        CLOSED = "closed", "Chiuso"

    month = models.DateField("mese", unique=True, help_text="Primo giorno del mese")
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField("chiuso il", null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+")
    reopen_reason = models.CharField("motivo dell'ultima riapertura", max_length=255, blank=True)
    notes = models.TextField("note per la rendicontazione", blank=True)

    class Meta:
        verbose_name = "mese delle presenze"
        verbose_name_plural = "mesi delle presenze"
        ordering = ["-month"]
        permissions = [("close_attendance", "Può chiudere e riaprire le presenze del mese")]

    def __str__(self):
        return f"Presenze {self.month:%m/%Y}"

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED


class AttendanceMonthRow(models.Model):
    """Presenze di un ospite nel mese chiuso: la base della rendicontazione e dei prospetti."""

    month = models.ForeignKey(AttendanceMonth, on_delete=models.CASCADE, related_name="rows")
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="+")
    days = models.JSONField("giorni", default=dict)  # {"1": "P", "2": "H", ...}
    present = models.PositiveSmallIntegerField("presenze", default=0)
    hospital = models.PositiveSmallIntegerField("assenze per ricovero", default=0)
    family = models.PositiveSmallIntegerField("assenze programmate / in famiglia", default=0)
    absent = models.PositiveSmallIntegerField("altre assenze", default=0)

    class Meta:
        verbose_name = "presenze mensili ospite"
        verbose_name_plural = "presenze mensili ospiti"
        constraints = [models.UniqueConstraint(fields=["month", "guest"], name="unique_attendance_row")]

    @property
    def in_care(self):
        return self.present + self.hospital + self.family + self.absent


class Payer(models.TextChoices):
    REGION = "region", "ATS / Regione (quota sanitaria)"
    MUNICIPALITY = "municipality", "Comune"
    GUEST = "guest", "Ospite / famiglia"
    OTHER = "other", "Altro ente"


def percent_field(label, default):
    return models.PositiveSmallIntegerField(label, default=default,
                                            validators=[MinValueValidator(0), MaxValueValidator(100)])


class GuestFeeLine(TimeStampedModel):
    """
    Una voce della retta di un ospite con il suo pagante, es. «Quota sanitaria – ATS» o «Quota sociale – Comune 60%».
    Per i giorni di assenza si applica la percentuale indicata (es. conservazione del posto).
    """

    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="fee_lines")
    description = models.CharField("voce", max_length=120, help_text="Es. Quota sanitaria, Quota sociale")
    payer = models.CharField("pagante", max_length=20, choices=Payer.choices)
    payer_name = models.CharField("intestatario", max_length=200,
                                  help_text="Es. ATS Città Metropolitana, Comune di Milano, Mario Rossi (ADS)")
    payer_tax_code = models.CharField("codice fiscale / partita IVA", max_length=30, blank=True)
    payer_address = models.CharField("indirizzo", max_length=255, blank=True)
    payer_email = models.EmailField("email / PEC", blank=True)
    daily_rate = models.DecimalField("tariffa giornaliera (€)", max_digits=9, decimal_places=2,
                                     validators=[MinValueValidator(Decimal("0"))])
    hospital_percent = percent_field("% durante il ricovero ospedaliero", 0)
    family_percent = percent_field("% durante rientri in famiglia / assenze programmate", 0)
    absent_percent = percent_field("% durante altre assenze", 0)
    max_absence_days = models.PositiveSmallIntegerField(
        "massimo giorni di assenza pagati nel mese", null=True, blank=True,
        help_text="Oltre questo numero i giorni di assenza non sono addebitati (vuoto = nessun limite)")
    valid_from = models.DateField("valida dal")
    valid_to = models.DateField("valida fino al", null=True, blank=True)
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta:
        verbose_name = "voce di retta"
        verbose_name_plural = "voci di retta"
        ordering = ["guest__last_name", "payer", "description"]

    def __str__(self):
        return f"{self.description} – {self.payer_name} ({self.daily_rate} €/giorno)"

    def percent_for(self, status):
        return {AttendanceStatus.PRESENT: 100, AttendanceStatus.HOSPITAL: self.hospital_percent,
                AttendanceStatus.FAMILY: self.family_percent, AttendanceStatus.ABSENT: self.absent_percent}.get(status, 0)

    def valid_on(self, day):
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


class StatementSequence(models.Model):
    """Numerazione progressiva senza salti dei prospetti emessi, per anno."""

    year = models.PositiveIntegerField(primary_key=True)
    last = models.PositiveIntegerField(default=0)


class FeeStatement(models.Model):
    """Prospetto mensile di retta per un ospite e un pagante (non è una fattura elettronica)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Bozza"
        ISSUED = "issued", "Emesso"
        PAID = "paid", "Pagato"
        CANCELLED = "cancelled", "Annullato"

    month = models.ForeignKey(AttendanceMonth, on_delete=models.PROTECT, related_name="statements")
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="fee_statements")
    payer = models.CharField("pagante", max_length=20, choices=Payer.choices)
    payer_name = models.CharField("intestatario", max_length=200)
    payer_tax_code = models.CharField("codice fiscale / partita IVA", max_length=30, blank=True)
    payer_address = models.CharField("indirizzo", max_length=255, blank=True)
    payer_email = models.EmailField("email / PEC", blank=True)
    lines = models.JSONField("righe", default=list)
    total = models.DecimalField("totale (€)", max_digits=11, decimal_places=2, default=Decimal("0"))
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.DRAFT)
    number = models.CharField("numero", max_length=20, blank=True, db_index=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    sequence = models.PositiveIntegerField(null=True, blank=True)
    issue_date = models.DateField("data di emissione", null=True, blank=True)
    due_date = models.DateField("scadenza", null=True, blank=True)
    notes = models.CharField("note", max_length=255, blank=True)
    cancel_reason = models.CharField("motivo annullamento", max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "prospetto di retta"
        verbose_name_plural = "prospetti di retta"
        ordering = ["-month__month", "guest__last_name", "payer_name"]
        permissions = [("issue_statement", "Può emettere e annullare i prospetti di retta")]
        constraints = [models.UniqueConstraint(fields=["year", "sequence"], condition=models.Q(sequence__isnull=False),
                                               name="unique_statement_number")]

    def __str__(self):
        return f"Prospetto {self.number or 'bozza'} – {self.guest} – {self.payer_name}"

    def get_absolute_url(self):
        return reverse("billing:statement", args=[self.pk])

    @property
    def paid_amount(self):
        return sum((p.amount for p in self.payments.all()), Decimal("0"))

    @property
    def balance(self):
        return self.total - self.paid_amount

    @property
    def is_overdue(self):
        return self.status == self.Status.ISSUED and self.due_date and self.due_date < timezone.localdate()


class FeePayment(models.Model):
    class Method(models.TextChoices):
        TRANSFER = "transfer", "Bonifico"
        DIRECT_DEBIT = "direct_debit", "Addebito diretto (SDD)"
        PAGOPA = "pagopa", "PagoPA"
        CARD = "card", "Carta / POS"
        CASH = "cash", "Contanti"
        OTHER = "other", "Altro"

    statement = models.ForeignKey(FeeStatement, on_delete=models.PROTECT, related_name="payments")
    date = models.DateField("data", default=timezone.localdate)
    amount = models.DecimalField("importo (€)", max_digits=11, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField("modalità", max_length=20, choices=Method.choices, default=Method.TRANSFER)
    reference = models.CharField("riferimento (CRO, causale…)", max_length=120, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "incasso"
        verbose_name_plural = "incassi"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.amount} € il {self.date:%d/%m/%Y}"
