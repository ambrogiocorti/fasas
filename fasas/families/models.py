"""
Area familiari e tutori (modulo spento di default: si accende dopo il parere del DPO).

Un familiare, un tutore o un amministratore di sostegno entra con un proprio utente (ruolo «Familiare o tutore»)
e vede SOLO gli ospiti a cui il coordinatore lo ha collegato, e solo ciò che il collegamento consente: messaggi con
la struttura, richieste di visita, documenti condivisi uno per uno, rendiconto della cassa personale (tutore).
Non vede mai la cartella clinica, i parametri, le terapie o il diario.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from fasas.core.models import TimeStampedModel


class FamilyLink(TimeStampedModel):
    class Relation(models.TextChoices):
        FAMILY = "family", "Familiare"
        GUARDIAN = "guardian", "Tutore"
        SUPPORT = "support", "Amministratore di sostegno"
        OTHER = "other", "Persona di riferimento indicata dall'ospite"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="utente del familiare", on_delete=models.PROTECT,
                             related_name="family_links")
    guest = models.ForeignKey("guests.Guest", verbose_name="ospite", on_delete=models.PROTECT,
                              related_name="family_links")
    relation = models.CharField("ruolo", max_length=10, choices=Relation.choices, default=Relation.FAMILY)
    description = models.CharField("parentela o qualifica", max_length=80, blank=True,
                                   help_text="Es. «figlia», «nipote», «avv. tutore nominato dal tribunale».")
    basis = models.CharField(
        "base del collegamento", max_length=255,
        help_text="Consenso dell'ospite (data e protocollo) oppure decreto di nomina del tutore o "
                  "dell'amministratore di sostegno. Senza base giuridica non si collega nessuno.")
    can_see_documents = models.BooleanField("vede i documenti condivisi", default=False)
    can_see_cash = models.BooleanField(
        "vede la cassa personale", default=False,
        help_text="Saldo e rendiconto della piccola cassa dell'ospite (di norma solo tutore o amministratore di sostegno).")
    active = models.BooleanField("attivo", default=True)
    revoked_at = models.DateTimeField("revocato il", null=True, blank=True, editable=False)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", editable=False)
    revoke_reason = models.CharField("motivo della revoca", max_length=255, blank=True, editable=False)

    class Meta:
        verbose_name = "collegamento familiare"
        verbose_name_plural = "collegamenti familiari"
        ordering = ["guest__last_name", "user__last_name"]
        constraints = [models.UniqueConstraint(fields=["user", "guest"], name="unique_family_link")]
        permissions = [
            ("use_family_area", "Usa l'area familiari come familiare o tutore"),
            ("manage_family_area", "Gestisce l'area familiari (collegamenti, messaggi, visite, documenti condivisi)"),
        ]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} → {self.guest} ({self.get_relation_display()})"


class FamilyMessage(models.Model):
    """Messaggio tra un familiare e la struttura: ogni collegamento ha la propria conversazione riservata."""

    link = models.ForeignKey(FamilyLink, on_delete=models.PROTECT, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    from_family = models.BooleanField(default=True)
    body = models.TextField("messaggio", max_length=2000)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    read_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+")

    class Meta:
        verbose_name = "messaggio dell'area familiari"
        verbose_name_plural = "messaggi dell'area familiari"
        ordering = ["created_at"]

    def __str__(self):
        return f"Messaggio {'dal familiare' if self.from_family else 'dalla struttura'} – {self.link.guest}"


class VisitRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "In attesa di conferma"
        CONFIRMED = "confirmed", "Confermata"
        DECLINED = "declined", "Non possibile"
        CANCELLED = "cancelled", "Annullata dal familiare"

    link = models.ForeignKey(FamilyLink, on_delete=models.PROTECT, related_name="visits")
    day = models.DateField("giorno")
    time = models.TimeField("ora")
    people = models.PositiveSmallIntegerField("persone", default=1)
    notes = models.CharField("note", max_length=255, blank=True)
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField("nota della struttura", max_length=255, blank=True)

    class Meta:
        verbose_name = "visita programmata"
        verbose_name_plural = "visite programmate"
        ordering = ["day", "time"]

    def __str__(self):
        return f"Visita {self.day:%d/%m/%Y} {self.time:%H:%M} – {self.link.guest}"


class SharedDocument(models.Model):
    """Documento che il coordinatore ha scelto di mostrare ai familiari autorizzati (sempre l'ultima versione)."""

    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="family_shares")
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    shared_at = models.DateTimeField(default=timezone.now)
    note = models.CharField("nota per i familiari", max_length=255, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")

    class Meta:
        verbose_name = "documento condiviso con i familiari"
        verbose_name_plural = "documenti condivisi con i familiari"
        ordering = ["-shared_at"]
        constraints = [models.UniqueConstraint(fields=["document"], condition=models.Q(revoked_at__isnull=True),
                                               name="unique_active_family_share")]

    def __str__(self):
        return f"{self.document} (condiviso)"
