from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import TimeStampedModel


class Appointment(TimeStampedModel):
    class Kind(models.TextChoices):
        MEDICAL = "medical", "Visita medica"
        EXAM = "exam", "Esame clinico"
        SPECIALIST = "specialist", "Visita specialistica"
        PHYSIOTHERAPY = "physiotherapy", "Fisioterapia"
        DENTAL = "dental", "Visita odontoiatrica"
        OTHER = "other", "Altro"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Programmato"
        DONE = "done", "Effettuato"
        CANCELLED = "cancelled", "Annullato"
        MISSED = "missed", "Non effettuato"

    guest = models.ForeignKey("guests.Guest", verbose_name="ospite", on_delete=models.PROTECT, related_name="appointments")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.MEDICAL)
    title = models.CharField("descrizione", max_length=200, help_text="Es. Visita neurologica di controllo")
    scheduled_at = models.DateTimeField("data e ora", db_index=True)
    location = models.CharField("luogo", max_length=200, blank=True)
    doctor = models.CharField("medico / specialista", max_length=150, blank=True)
    companion = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="accompagnatore (operatore)", on_delete=models.PROTECT,
        null=True, blank=True, related_name="accompanied_appointments",
    )
    companion_name = models.CharField("accompagnatore (esterno)", max_length=150, blank=True)
    transport = models.CharField("trasporto", max_length=150, blank=True)
    preparation = models.TextField("preparazione richiesta (digiuno, documenti...)", blank=True)
    status = models.CharField("stato", max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    outcome = models.TextField("esito della visita", blank=True)
    follow_up = models.TextField("indicazioni / controlli successivi", blank=True)
    document = models.ForeignKey(
        "documents.Document", verbose_name="documento allegato (referto)", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    reminded_day_before = models.BooleanField(default=False, editable=False)
    reminded_same_day = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = "appuntamento sanitario"
        verbose_name_plural = "appuntamenti sanitari"
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.title} – {self.guest} – {timezone.localtime(self.scheduled_at):%d/%m/%Y %H:%M}"

    def get_absolute_url(self):
        return reverse("appointments:detail", args=[self.pk])

    @property
    def companion_display(self):
        return str(self.companion) if self.companion else self.companion_name
