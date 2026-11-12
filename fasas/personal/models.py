"""
Denaro e oggetti personali degli ospiti (registro della «piccola cassa» e inventario degli effetti personali).
I movimenti non si cancellano: si annullano con motivo, come le registrazioni sanitarie. Gli scontrini sono
cifrati come i documenti. Non contiene dati sanitari: lo usano anche l'ufficio amministrativo e il tutore.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import TimeStampedModel


class CashMovementQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(voided_at__isnull=True)

    def balance(self):
        totals = self.valid().aggregate(
            inflow=Sum("amount", filter=Q(kind=CashMovement.Kind.DEPOSIT)),
            outflow=Sum("amount", filter=~Q(kind=CashMovement.Kind.DEPOSIT)))
        return (totals["inflow"] or Decimal("0")) - (totals["outflow"] or Decimal("0"))


class CashMovement(TimeStampedModel):
    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "Versamento"
        EXPENSE = "expense", "Spesa"
        WITHDRAWAL = "withdrawal", "Contanti consegnati all'ospite"
        RETURN = "return", "Restituzione al familiare o tutore"

    guest = models.ForeignKey("guests.Guest", verbose_name="ospite", on_delete=models.PROTECT,
                              related_name="cash_movements")
    occurred_on = models.DateField("data", default=timezone.localdate)
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices)
    amount = models.DecimalField("importo (€)", max_digits=9, decimal_places=2)
    description = models.CharField("descrizione", max_length=255,
                                   help_text="Es. «versamento della sorella», «parrucchiere», «ricarica telefono».")
    counterpart = models.CharField("da / a chi", max_length=120, blank=True)
    receipt_storage = models.CharField(max_length=255, blank=True, editable=False)
    receipt_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    receipt_type = models.CharField(max_length=60, blank=True, editable=False)
    voided_at = models.DateTimeField("annullato il", null=True, blank=True, editable=False)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+", editable=False)
    void_reason = models.CharField("motivo annullamento", max_length=255, blank=True, editable=False)

    objects = CashMovementQuerySet.as_manager()

    class Meta:
        verbose_name = "movimento di cassa"
        verbose_name_plural = "movimenti di cassa"
        ordering = ["-occurred_on", "-created_at"]
        permissions = [("void_cashmovement", "Può annullare un movimento di cassa (con motivo)")]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} € – {self.guest} ({self.occurred_on:%d/%m/%Y})"

    @property
    def is_voided(self):
        return self.voided_at is not None

    @property
    def signed_amount(self):
        return self.amount if self.kind == self.Kind.DEPOSIT else -self.amount

    def get_absolute_url(self):
        return reverse("personal:guest", args=[self.guest_id])


class PersonalItem(TimeStampedModel):
    class Status(models.TextChoices):
        PRESENT = "present", "In struttura"
        RETURNED = "returned", "Restituito"
        LOST = "lost", "Smarrito"
        DISPOSED = "disposed", "Eliminato (consumato o rotto)"

    guest = models.ForeignKey("guests.Guest", verbose_name="ospite", on_delete=models.PROTECT,
                              related_name="personal_items")
    name = models.CharField("oggetto", max_length=150, help_text="Es. «orologio da polso», «radio», «carrozzina».")
    description = models.CharField("descrizione", max_length=255, blank=True,
                                   help_text="Marca, colore, segni particolari.")
    quantity = models.PositiveSmallIntegerField("quantità", default=1)
    value = models.DecimalField("valore indicativo (€)", max_digits=9, decimal_places=2, null=True, blank=True)
    received_on = models.DateField("consegnato il", default=timezone.localdate)
    received_from = models.CharField("consegnato da", max_length=120, blank=True)
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.PRESENT)
    status_date = models.DateField("data dello stato", null=True, blank=True)
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta:
        verbose_name = "oggetto personale"
        verbose_name_plural = "oggetti personali"
        ordering = ["status", "name"]

    def __str__(self):
        return f"{self.name} – {self.guest}"

    def get_absolute_url(self):
        return reverse("personal:guest", args=[self.guest_id])
