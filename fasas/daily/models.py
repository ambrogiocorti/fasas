from django.conf import settings
from django.db import models
from django.utils import timezone

from fasas.core.models import ShiftRecordModel
from fasas.core.shifts import Shift


class ShiftAssignment(models.Model):
    """Registro turni operatori: chi era in servizio in ogni turno."""

    date = models.DateField("data", db_index=True)
    shift = models.CharField("turno", max_length=1, choices=Shift.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="operatore", on_delete=models.PROTECT,
                             related_name="shift_assignments")
    is_shift_lead = models.BooleanField("responsabile di turno", default=False)
    checked_in_at = models.DateTimeField("presa servizio", null=True, blank=True)
    checked_out_at = models.DateTimeField("fine servizio", null=True, blank=True)
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta:
        verbose_name = "turno operatore"
        verbose_name_plural = "registro turni"
        ordering = ["-date", "shift", "user__last_name"]
        constraints = [models.UniqueConstraint(fields=["date", "shift", "user"], name="unique_shift_assignment")]

    def __str__(self):
        return f"{self.date:%d/%m/%Y} {self.get_shift_display()} – {self.user}"


class ShiftClosure(models.Model):
    """Blocco giornata: un turno chiuso non accetta più inserimenti né modifiche."""

    date = models.DateField("data", db_index=True)
    shift = models.CharField("turno", max_length=1, choices=Shift.choices)
    closed_at = models.DateTimeField("chiuso il", default=timezone.now)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+")
    automatic = models.BooleanField("chiusura automatica", default=False)
    summary = models.JSONField("riepilogo alla chiusura", default=dict, blank=True)
    handover_notes = models.TextField("consegne per il turno successivo", blank=True)
    reopened_at = models.DateTimeField("riaperto il", null=True, blank=True)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+")
    reopen_reason = models.TextField("motivo riapertura", blank=True)

    class Meta:
        verbose_name = "chiusura turno"
        verbose_name_plural = "chiusure turno"
        ordering = ["-date", "-shift"]
        constraints = [models.UniqueConstraint(fields=["date", "shift"], name="unique_shift_closure")]
        permissions = [
            ("close_shift", "Può chiudere un turno"),
            ("reopen_shift", "Può riaprire in via straordinaria un turno chiuso"),
        ]

    def __str__(self):
        return f"Chiusura {self.date:%d/%m/%Y} {self.get_shift_display()}"

    @property
    def is_closed(self):
        return self.reopened_at is None


class DailyRecord(ShiftRecordModel):
    """Registro giornaliero: alimentazione, igiene, comportamento, attività, sonno, note."""

    class Category(models.TextChoices):
        MEAL = "meal", "Alimentazione"
        HYDRATION = "hydration", "Idratazione"
        HYGIENE = "hygiene", "Igiene personale"
        BEHAVIOUR = "behaviour", "Comportamento"
        ACTIVITY = "activity", "Attività svolte"
        SLEEP = "sleep", "Sonno / riposo"
        MOBILIZATION = "mobilization", "Mobilizzazione / postura"
        NOTE = "note", "Note assistenziali"

    class Meal(models.TextChoices):
        BREAKFAST = "breakfast", "Colazione"
        LUNCH = "lunch", "Pranzo"
        SNACK = "snack", "Merenda"
        DINNER = "dinner", "Cena"

    class Intake(models.TextChoices):
        ALL = "100", "Tutto"
        THREE_QUARTERS = "75", "3/4"
        HALF = "50", "Metà"
        QUARTER = "25", "1/4"
        NONE = "0", "Nulla / rifiutato"

    category = models.CharField("categoria", max_length=20, choices=Category.choices)
    meal = models.CharField("pasto", max_length=20, choices=Meal.choices, blank=True)
    intake = models.CharField("quantità assunta", max_length=3, choices=Intake.choices, blank=True)
    description = models.TextField("descrizione", blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "registrazione giornaliera"
        verbose_name_plural = "registro giornaliero"

    def __str__(self):
        label = self.get_meal_display() if self.meal else self.get_category_display()
        return f"{label} – {self.guest} – {timezone.localtime(self.occurred_at):%d/%m %H:%M}"


class EvacuationRecord(ShiftRecordModel):
    class Consistency(models.TextChoices):
        B1 = "1", "Bristol 1 – grumi duri"
        B2 = "2", "Bristol 2 – salsiccia grumosa"
        B3 = "3", "Bristol 3 – salsiccia con crepe"
        B4 = "4", "Bristol 4 – liscia e morbida"
        B5 = "5", "Bristol 5 – pezzi morbidi"
        B6 = "6", "Bristol 6 – pastosa"
        B7 = "7", "Bristol 7 – liquida"

    class Amount(models.TextChoices):
        SCARCE = "scarce", "Scarsa"
        NORMAL = "normal", "Normale"
        ABUNDANT = "abundant", "Abbondante"

    outcome = models.BooleanField("evacuazione avvenuta", default=True)
    consistency = models.CharField("consistenza (scala di Bristol)", max_length=1, choices=Consistency.choices, blank=True)
    amount = models.CharField("quantità", max_length=10, choices=Amount.choices, blank=True)
    assisted = models.BooleanField("dopo intervento (lassativo/lavanda)", default=False)
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "evacuazione"
        verbose_name_plural = "evacuazioni"

    def __str__(self):
        return f"Evacuazione {'SI' if self.outcome else 'NO'} – {self.guest} – {self.shift_date:%d/%m/%Y}"


class DiaryEntry(ShiftRecordModel):
    """Diario assistenziale: note libere degli operatori."""

    text = models.TextField("nota")
    is_relevant = models.BooleanField("clinicamente rilevante (da segnalare)", default=False)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "nota di diario"
        verbose_name_plural = "diario assistenziale"

    def __str__(self):
        return f"Diario {self.guest} {timezone.localtime(self.occurred_at):%d/%m/%Y %H:%M}"


class ChecklistTemplate(models.Model):
    name = models.CharField("nome", max_length=120)
    shift = models.CharField("turno", max_length=1, choices=Shift.choices)
    active = models.BooleanField("attiva", default=True)

    class Meta:
        verbose_name = "checklist di turno"
        verbose_name_plural = "checklist di turno"
        ordering = ["shift", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_shift_display()})"


class ChecklistItem(models.Model):
    class CheckType(models.TextChoices):
        MANUAL = "manual", "Spunta manuale"
        THERAPY = "therapy", "Automatico: farmaci del turno registrati"
        PARAMETERS = "parameters", "Automatico: parametri rilevati nel turno"
        MEAL = "meal", "Automatico: pasto registrato"
        HYGIENE = "hygiene", "Automatico: igiene registrata"
        EVACUATION = "evacuation", "Automatico: evacuazione registrata (modalità A)"

    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="items")
    label = models.CharField("voce", max_length=150)
    check_type = models.CharField("tipo di verifica", max_length=20, choices=CheckType.choices, default=CheckType.MANUAL)
    meal = models.CharField("pasto", max_length=20, choices=DailyRecord.Meal.choices, blank=True)
    parameter_type = models.ForeignKey(
        "clinical.ParameterType", verbose_name="parametro", on_delete=models.SET_NULL, null=True, blank=True
    )
    per_guest = models.BooleanField("da verificare per ogni ospite", default=True)
    required_tags = models.ManyToManyField(
        "guests.ClinicalTag", verbose_name="solo per ospiti con tag", blank=True,
        help_text="Es. glicemia solo per ospiti con tag «diabetico»",
    )
    order = models.PositiveSmallIntegerField("ordine", default=0)

    class Meta:
        verbose_name = "voce di checklist"
        verbose_name_plural = "voci di checklist"
        ordering = ["order", "pk"]

    def __str__(self):
        return self.label


class ChecklistCheck(models.Model):
    date = models.DateField("data")
    shift = models.CharField("turno", max_length=1, choices=Shift.choices)
    item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT, related_name="checks")
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    not_applicable = models.BooleanField("non applicabile", default=False)
    notes = models.CharField("note", max_length=255, blank=True)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    done_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "spunta checklist"
        verbose_name_plural = "spunte checklist"
        constraints = [
            models.UniqueConstraint(fields=["date", "shift", "item", "guest"], name="unique_checklist_check")
        ]

    def __str__(self):
        return f"{self.item} {self.date} {self.shift}"
