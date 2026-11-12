"""
Attività assistenziali a orario per ospite: riposizionamenti, idratazione, controlli notturni, igiene...
Il piano (CareTask) dice cosa fare e quando; ogni esecuzione (CareTaskCheck) si spunta nel turno ed è una
registrazione come le altre: legata al turno, mai cancellata, annullabile solo con motivo.
Gli orari e le istruzioni sono quelli decisi dall'équipe: il FASAS li ricorda, non li suggerisce.
"""
import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import ShiftRecordModel, TimeStampedModel
from fasas.core.shifts import Shift


def parse_time(value):
    try:
        return datetime.datetime.strptime(str(value).strip(), "%H:%M").time()
    except ValueError as exc:
        raise ValidationError(f"Orario non valido: «{value}» (usare HH:MM, es. 08:00).") from exc


class CareTask(TimeStampedModel):
    class Kind(models.TextChoices):
        REPOSITIONING = "repositioning", "Riposizionamento / cambio postura"
        HYDRATION = "hydration", "Idratazione"
        NIGHT_CHECK = "night_check", "Controllo notturno"
        CONTINENCE = "continence", "Bagno / cambio ausilio per l'incontinenza"
        MOBILIZATION = "mobilization", "Mobilizzazione / passeggiata"
        SKIN = "skin", "Controllo della cute"
        OTHER = "other", "Altra attività"

    guest = models.ForeignKey("guests.Guest", verbose_name="ospite", on_delete=models.PROTECT,
                              related_name="care_tasks")
    kind = models.CharField("attività", max_length=20, choices=Kind.choices)
    label = models.CharField("nome (facoltativo)", max_length=120, blank=True,
                             help_text="Es. «Acqua o tisana, almeno 150 ml». Vuoto = nome dell'attività.")
    instructions = models.TextField("istruzioni dell'équipe", blank=True,
                                    help_text="Es. alternare fianco destro, sinistro e supino; cuscino tra le ginocchia.")
    times = models.JSONField("orari fissi", default=list, blank=True,
                             help_text="Orari HH:MM separati da virgola (es. 10:00, 15:00, 21:00).")
    every_hours = models.PositiveSmallIntegerField("oppure ogni quante ore", null=True, blank=True,
                                                   help_text="Es. 2 per «ogni 2 ore». Con l'ora della prima volta.")
    first_time = models.TimeField("prima volta alle", null=True, blank=True)
    shifts = models.JSONField("solo in questi turni", default=list, blank=True,
                              help_text="Vuoto = in tutti i turni (es. solo notte per i controlli notturni).")
    late_minutes = models.PositiveSmallIntegerField("in ritardo dopo (minuti)", default=30)
    start_date = models.DateField("dal", default=timezone.localdate)
    end_date = models.DateField("al (facoltativo)", null=True, blank=True)
    active = models.BooleanField("attiva", default=True)
    end_reason = models.CharField("motivo della fine", max_length=255, blank=True)

    class Meta:
        verbose_name = "attività a orario"
        verbose_name_plural = "attività a orario"
        ordering = ["guest__last_name", "kind"]

    def __str__(self):
        return f"{self.name} – {self.guest}"

    @property
    def name(self):
        return self.label or self.get_kind_display()

    def get_absolute_url(self):
        return reverse("care:guest", args=[self.guest_id])

    def clean(self):
        times = [parse_time(t) for t in (self.times or [])]
        if bool(times) == bool(self.every_hours):
            raise ValidationError("Indicare gli orari fissi oppure «ogni quante ore» (non tutti e due).")
        if self.every_hours and not (1 <= self.every_hours <= 12):
            raise ValidationError({"every_hours": "Da 1 a 12 ore."})
        if self.every_hours and self.first_time is None:
            raise ValidationError({"first_time": "Indicare l'ora della prima volta."})
        if any(s not in Shift.values for s in self.shifts or []):
            raise ValidationError({"shifts": "Turno non valido."})
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La fine precede l'inizio."})

    def parsed_times(self):
        """Orari previsti nella giornata (ora locale), già filtrati per i turni scelti."""
        from fasas.core.shifts import time_in_shift

        if self.every_hours and self.first_time:
            start = datetime.datetime.combine(datetime.date(2000, 1, 1), self.first_time)
            values = {(start + datetime.timedelta(hours=self.every_hours * k)).time()
                      for k in range(24 // self.every_hours)}
        else:
            values = {parse_time(t) for t in self.times or []}
        if self.shifts:
            values = {t for t in values if any(time_in_shift(t, s) for s in self.shifts)}
        return sorted(values)

    def schedule_display(self):
        if self.every_hours:
            text = f"ogni {self.every_hours} ore dalle {self.first_time:%H:%M}"
        else:
            text = ", ".join(t.strftime("%H:%M") for t in self.parsed_times())
        if self.shifts:
            text += " · solo " + ", ".join(Shift(s).label.lower() for s in self.shifts)
        return text

    def is_active_on(self, day):
        return self.active and self.start_date <= day and (self.end_date is None or day <= self.end_date)


class CareTaskCheck(ShiftRecordModel):
    class Status(models.TextChoices):
        DONE = "done", "Fatta"
        NOT_DONE = "not_done", "Non fatta"
        REFUSED = "refused", "Rifiutata dall'ospite"

    task = models.ForeignKey(CareTask, verbose_name="attività", on_delete=models.PROTECT, related_name="checks")
    scheduled_date = models.DateField("giorno previsto")
    scheduled_time = models.TimeField("ora prevista")
    status = models.CharField("esito", max_length=10, choices=Status.choices, default=Status.DONE)
    notes = models.CharField("note", max_length=500, blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "attività eseguita"
        verbose_name_plural = "attività eseguite"
        constraints = [models.UniqueConstraint(
            fields=["task", "scheduled_date", "scheduled_time"], condition=models.Q(voided_at__isnull=True),
            name="unique_care_task_check")]

    def __str__(self):
        return f"{self.task.name} delle {self.scheduled_time:%H:%M} – {self.guest} ({self.get_status_display().lower()})"

    def get_absolute_url(self):
        return reverse("care:guest", args=[self.guest_id])
