from django.conf import settings
from django.db import models
from django.urls import reverse

from fasas.core.models import TimeStampedModel


class PAI(TimeStampedModel):
    """Piano Assistenziale Individuale, versionato: ogni revisione crea una nuova versione."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Bozza"
        ACTIVE = "active", "In vigore"
        SUPERSEDED = "superseded", "Superato da revisione"

    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="pais")
    version = models.PositiveIntegerField("versione")
    status = models.CharField("stato", max_length=20, choices=Status.choices, default=Status.DRAFT)
    valid_from = models.DateField("in vigore dal", null=True, blank=True)
    review_due = models.DateField("prossima revisione entro")
    summary = models.TextField("sintesi / bisogni rilevati", blank=True)
    participants = models.TextField("partecipanti alla stesura (équipe, familiari, tutore)", blank=True)
    previous = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="revisions")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    document = models.ForeignKey("documents.Document", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", help_text="PDF del PAI archiviato tra i documenti")

    class Meta:
        verbose_name = "PAI"
        verbose_name_plural = "PAI"
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["guest", "version"], name="unique_pai_version")]
        permissions = [("approve_pai", "Può approvare e mettere in vigore un PAI")]

    def __str__(self):
        return f"PAI v{self.version} – {self.guest}"

    def get_absolute_url(self):
        return reverse("pai:detail", args=[self.pk])

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT and not self.guest.is_archived


class PAIGoal(models.Model):
    class Area(models.TextChoices):
        HEALTH = "health", "Area sanitaria"
        AUTONOMY = "autonomy", "Area autonomia"
        BEHAVIOUR = "behaviour", "Area comportamentale"
        SOCIAL = "social", "Area sociale / relazionale"

    class Outcome(models.TextChoices):
        ONGOING = "ongoing", "In corso"
        ACHIEVED = "achieved", "Raggiunto"
        PARTIAL = "partial", "Parzialmente raggiunto"
        NOT_ACHIEVED = "not_achieved", "Non raggiunto"
        SUSPENDED = "suspended", "Sospeso"

    pai = models.ForeignKey(PAI, on_delete=models.CASCADE, related_name="goals")
    area = models.CharField("area", max_length=20, choices=Area.choices)
    objective = models.TextField("obiettivo")
    intervention = models.TextField("intervento")
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="operatore responsabile",
                                    on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    responsible_name = models.CharField("responsabile (se esterno)", max_length=150, blank=True)
    verification_date = models.DateField("data verifica")
    indicators = models.CharField("indicatori di verifica", max_length=255, blank=True)
    outcome = models.CharField("esito", max_length=20, choices=Outcome.choices, default=Outcome.ONGOING)
    verification_notes = models.TextField("note di verifica", blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "obiettivo PAI"
        verbose_name_plural = "obiettivi PAI"
        ordering = ["area", "order", "pk"]

    def __str__(self):
        return f"{self.get_area_display()}: {self.objective[:60]}"

    @property
    def guest(self):
        return self.pai.guest

    @property
    def responsible_display(self):
        return str(self.responsible) if self.responsible else self.responsible_name
