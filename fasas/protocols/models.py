from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import TimeStampedModel


class Protocol(TimeStampedModel):
    """
    Protocollo sanitario automatico: una regola che, quando si verifica, genera
    attivazione, notifica, avviso in dashboard e la lista delle azioni richieste.

    I parametri predefiniti sono esempi: vanno validati dal medico/direttore sanitario
    della struttura prima dell'uso.
    """

    class Kind(models.TextChoices):
        EVACUATION = "evacuation", "Evacuazione"
        FEVER = "fever", "Febbre"
        GLYCEMIA = "glycemia", "Glicemia"
        SEIZURE = "seizure", "Crisi epilettica"
        AGITATION = "agitation", "Agitazione"
        SOS = "sos", "Farmaci SOS"

    DEFAULT_PARAMS = {
        Kind.EVACUATION: {"days": 3},
        Kind.FEVER: {"threshold": 37.5, "parameter": "temperatura"},
        Kind.GLYCEMIA: {"min": 70, "max": 250, "parameter": "glicemia"},
        Kind.SEIZURE: {"min_duration_minutes": 0},
        Kind.AGITATION: {"events": 1, "window_hours": 24},
        Kind.SOS: {"count": 2, "window_hours": 24},
    }

    PARAM_HELP = {
        Kind.EVACUATION: "days = giorni senza evacuazione che attivano il protocollo",
        Kind.FEVER: "threshold = temperatura (°C) oltre cui si attiva; parameter = codice del tipo parametro",
        Kind.GLYCEMIA: "min/max = limiti glicemia (mg/dL); parameter = codice del tipo parametro",
        Kind.SEIZURE: "min_duration_minutes = durata minima della crisi che attiva il protocollo (0 = ogni crisi)",
        Kind.AGITATION: "events = numero di episodi nella finestra; window_hours = finestra in ore",
        Kind.SOS: "count = somministrazioni SOS nella finestra; window_hours = finestra in ore",
    }

    class Severity(models.TextChoices):
        INFO = "info", "Informazione"
        WARNING = "warning", "Attenzione"
        CRITICAL = "critical", "Critica"

    name = models.CharField("nome", max_length=150)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    description = models.TextField("descrizione", blank=True)
    params = models.JSONField("parametri della regola", default=dict, blank=True)
    actions = models.TextField(
        "azioni richieste", help_text="Una per riga, es. «Somministrare lassativo come da prescrizione»"
    )
    severity = models.CharField("priorità", max_length=10, choices=Severity.choices, default=Severity.WARNING)
    applies_to_all = models.BooleanField("si applica a tutti gli ospiti", default=True)
    tags = models.ManyToManyField("guests.ClinicalTag", verbose_name="solo ospiti con tag", blank=True)
    guests = models.ManyToManyField("guests.Guest", verbose_name="solo questi ospiti", blank=True,
                                    related_name="specific_protocols")
    notify_roles = models.JSONField("ruoli da avvisare", default=list, blank=True,
                                    help_text="Vuoto = impostazioni generali delle notifiche")
    validated_by = models.CharField("validato da (medico / direttore sanitario)", max_length=150, blank=True)
    validated_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="validato da (utente)",
                                          on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    validated_at = models.DateTimeField("validato il", null=True, blank=True)
    active = models.BooleanField("attivo", default=True)

    # Cambiare questi campi richiede una nuova validazione del medico
    CLINICAL_FIELDS = ("kind", "params", "actions", "severity")

    class Meta:
        verbose_name = "protocollo"
        verbose_name_plural = "protocolli"
        ordering = ["kind", "name"]
        permissions = [("validate_protocol", "Può validare soglie e azioni dei protocolli (medico della struttura)")]

    @property
    def is_validated(self):
        return self.validated_at is not None

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("protocols:update", args=[self.pk])

    @property
    def action_list(self):
        return [line.strip() for line in self.actions.splitlines() if line.strip()]

    def param(self, key):
        value = (self.params or {}).get(key)
        if value is None:
            value = self.DEFAULT_PARAMS.get(self.kind, {}).get(key)
        return value

    def applies_to(self, guest):
        if not self.active or (settings.FASAS_PROTOCOLS_REQUIRE_VALIDATION and not self.is_validated):
            return False
        if self.applies_to_all:
            return True
        if self.guests.filter(pk=guest.pk).exists():
            return True
        tag_ids = set(self.tags.values_list("pk", flat=True))
        return bool(tag_ids & set(guest.tags.values_list("pk", flat=True)))


class ProtocolActivation(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Da gestire"
        IN_PROGRESS = "in_progress", "In corso"
        RESOLVED = "resolved", "Risolto"
        DISMISSED = "dismissed", "Archiviato (non necessario)"

    OPEN_STATES = (Status.OPEN, Status.IN_PROGRESS)

    protocol = models.ForeignKey(Protocol, on_delete=models.PROTECT, related_name="activations")
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, related_name="protocol_activations")
    triggered_at = models.DateTimeField("attivato il", default=timezone.now, db_index=True)
    trigger_summary = models.CharField("motivo attivazione", max_length=255)
    trigger_data = models.JSONField(default=dict, blank=True)
    status = models.CharField("stato", max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolved_at = models.DateTimeField("chiuso il", null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+")
    resolution_notes = models.TextField("esito / note di chiusura", blank=True)
    auto_resolved = models.BooleanField("risolto automaticamente", default=False)

    class Meta:
        verbose_name = "attivazione protocollo"
        verbose_name_plural = "attivazioni protocolli"
        ordering = ["-triggered_at"]

    def __str__(self):
        return f"{self.protocol} – {self.guest} ({self.triggered_at:%d/%m/%Y %H:%M})"

    def get_absolute_url(self):
        return reverse("protocols:activation_detail", args=[self.pk])

    @property
    def is_open(self):
        return self.status in self.OPEN_STATES

    def actions_status(self):
        done = {log.action_label: log for log in self.action_logs.all()}
        return [{"label": label, "log": done.get(label)} for label in self.protocol.action_list]


class ProtocolActionLog(models.Model):
    activation = models.ForeignKey(ProtocolActivation, on_delete=models.CASCADE, related_name="action_logs")
    action_label = models.CharField("azione", max_length=255)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    done_at = models.DateTimeField("eseguita il", default=timezone.now)
    notes = models.CharField("note / esito", max_length=255, blank=True)

    class Meta:
        verbose_name = "azione eseguita"
        verbose_name_plural = "azioni eseguite"
        ordering = ["done_at"]

    def __str__(self):
        return self.action_label

    @property
    def guest(self):
        return self.activation.guest
