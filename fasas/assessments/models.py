from django.db import models
from django.urls import reverse

from fasas.core.models import ShiftRecordModel

from .scales import SCALE_CHOICES, SCALES


class ScaleSetting(models.Model):
    """Quali scale usa la struttura e ogni quanti giorni vanno ripetute (0 = solo al bisogno)."""

    code = models.CharField("scala", max_length=20, choices=SCALE_CHOICES, unique=True)
    enabled = models.BooleanField("in uso nella struttura", default=True)
    interval_days = models.PositiveSmallIntegerField("ripetere ogni (giorni, 0 = al bisogno)", default=0)

    class Meta:
        verbose_name = "impostazione scala"
        verbose_name_plural = "impostazioni scale"
        ordering = ["code"]

    def __str__(self):
        return self.get_code_display()

    @property
    def scale(self):
        return SCALES[self.code]


class Assessment(ShiftRecordModel):
    """Una valutazione con una scala: punteggi delle voci, totale e fascia come sulla scheda cartacea."""

    scale = models.CharField("scala", max_length=20, choices=SCALE_CHOICES, db_index=True)
    answers = models.JSONField("punteggi delle voci", default=dict)
    total = models.IntegerField("punteggio totale")
    band = models.CharField("fascia", max_length=80)
    band_level = models.CharField(max_length=10, default="ok")
    next_due = models.DateField("da ripetere entro", null=True, blank=True)
    notes = models.TextField("note", blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "valutazione"
        verbose_name_plural = "valutazioni"

    def __str__(self):
        return f"{self.get_scale_display()} {self.total} – {self.guest} – {self.occurred_at:%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("assessments:detail", args=[self.pk])

    @property
    def scale_def(self):
        return SCALES[self.scale]

    def answer_rows(self):
        rows = []
        for item in self.scale_def.items:
            points = self.answers.get(item.key)
            label = dict(item.options).get(points, "")
            rows.append({"item": item, "points": points, "label": label})
        return rows
