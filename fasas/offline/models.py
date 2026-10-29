from django.conf import settings
from django.db import models
from django.utils import timezone


class OfflineRecord(models.Model):
    """
    Ricevuta di una registrazione fatta senza rete e sincronizzata dopo. L'identificativo generato dal
    dispositivo rende la sincronizzazione ripetibile senza duplicati; la registrazione vera (somministrazione,
    parametro, diario, evento) è nel suo modello, con audit di origine «offline».
    """

    class Kind(models.TextChoices):
        ADMINISTRATION = "administration", "Somministrazione"
        SOS = "sos", "Farmaco SOS"
        PARAMETER = "parameter", "Parametro"
        DIARY = "diary", "Diario"
        EVENT = "event", "Evento"
        OTHER = "other", "Non riconosciuta"

    class Status(models.TextChoices):
        OK = "ok", "Registrata"
        LATE = "late", "Registrata in un turno già chiuso"
        CONFLICT = "conflict", "Già registrata da un altro operatore"
        REJECTED = "rejected", "Non registrata"

    uuid = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    occurred_at = models.DateTimeField("avvenuta il")
    received_at = models.DateTimeField("sincronizzata il", default=timezone.now)
    status = models.CharField("esito", max_length=20, choices=Status.choices)
    message = models.CharField("dettaglio", max_length=500, blank=True)
    payload = models.JSONField("dati ricevuti", default=dict)
    object_label = models.CharField("registrazione creata", max_length=255, blank=True)

    class Meta:
        permissions = [("use_offline", "Può lavorare in modalità offline sul dispositivo")]
        verbose_name = "registrazione offline"
        verbose_name_plural = "registrazioni offline"
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.get_kind_display()} offline {self.occurred_at:%d/%m %H:%M} ({self.get_status_display()})"
