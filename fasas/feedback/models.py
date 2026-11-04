from django.conf import settings
from django.db import models
from django.utils import timezone


class Feedback(models.Model):
    """
    Segnalazione di un utente durante il pilota: cosa non va, cosa è scomodo, cosa manca. Si salvano la pagina
    (solo il percorso, senza parametri) e l'ora; il testo non deve contenere dati sanitari o nomi degli ospiti.
    """

    class Kind(models.TextChoices):
        ERROR = "error", "Non funziona / dà errore"
        HARD = "hard", "Scomodo, lento o poco chiaro"
        MISSING = "missing", "Manca qualcosa"
        IDEA = "idea", "Suggerimento"

    class Status(models.TextChoices):
        NEW = "new", "Da guardare"
        TAKEN = "taken", "Presa in carico"
        DONE = "done", "Risolta"
        DECLINED = "declined", "Non si cambia"

    OPEN = (Status.NEW, Status.TAKEN)

    created_at = models.DateTimeField("inviata il", default=timezone.now, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="da", on_delete=models.PROTECT,
                                   related_name="feedback", editable=False)
    role = models.CharField("ruolo", max_length=30, blank=True, editable=False)
    page = models.CharField("pagina", max_length=300, blank=True)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.HARD)
    text = models.TextField("cosa è successo")
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.NEW)
    reply = models.TextField("risposta o decisione", blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", editable=False)
    handled_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "segnalazione"
        verbose_name_plural = "segnalazioni"
        ordering = ["-created_at"]
        permissions = [("view_pilot_metrics", "Può vedere gli indicatori del pilota")]

    def __str__(self):
        return f"{self.get_kind_display()} del {timezone.localtime(self.created_at):%d/%m/%Y %H:%M}"
