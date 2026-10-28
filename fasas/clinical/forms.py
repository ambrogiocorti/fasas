import datetime
import re

from django import forms
from django.utils import timezone

from fasas.accounts.models import Role, User
from fasas.guests.forms import DateInput, DateTimeInput
from fasas.pharmacy.models import Drug

from .models import ClinicalEvent, ParameterReading, ParameterType, Restraint, Therapy, TherapyAdministration


class ScheduleTimesField(forms.CharField):
    """Orari separati da virgola o spazio: «08:00, 13:00, 20:00»."""

    def prepare_value(self, value):
        if isinstance(value, list):
            return ", ".join(value)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        times = []
        for part in re.split(r"[,\s;]+", value or ""):
            if not part:
                continue
            part = part.replace(".", ":")
            if re.fullmatch(r"\d{1,2}", part):
                part = f"{part}:00"
            try:
                parsed = datetime.datetime.strptime(part, "%H:%M").time()
            except ValueError:
                raise forms.ValidationError(f"Orario non valido: {part}. Usa il formato HH:MM.") from None
            times.append(parsed.strftime("%H:%M"))
        return sorted(set(times))


class TherapyForm(forms.ModelForm):
    schedule_times = ScheduleTimesField(label="Orari", required=False, help_text="Es. 08:00, 13:00, 20:00")
    confirm_warnings = forms.BooleanField(
        label="Ho verificato gli avvisi e confermo la prescrizione", required=False
    )

    class Meta:
        model = Therapy
        fields = [
            "drug", "dose", "dose_unit", "stock_units_per_dose", "route", "is_sos", "schedule_times", "every_n_days",
            "start_date", "end_date", "instructions", "sos_indication", "sos_max_daily", "sos_min_interval_hours",
            "sos_requires_validation", "prescriber", "prescriber_name", "prescription_date", "prescription_document",
        ]
        widgets = {
            "start_date": DateInput(), "end_date": DateInput(), "prescription_date": DateInput(),
            "instructions": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, guest=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.guest = guest
        self.warnings = []
        self.fields["drug"].queryset = Drug.objects.filter(active=True)
        self.fields["prescriber"].queryset = User.objects.filter(role=Role.DOCTOR, is_active=True)
        if guest is not None:
            self.fields["prescription_document"].queryset = guest.documents.filter(category__in=["prescription", "medical_report"])

    def clean(self):
        cleaned = super().clean()
        drug = cleaned.get("drug")
        if drug and self.guest is not None:
            from .services import check_therapy_conflicts

            self.warnings = check_therapy_conflicts(self.guest, drug, exclude_therapy=self.instance)
            if self.warnings and not cleaned.get("confirm_warnings"):
                raise forms.ValidationError(
                    "Sono presenti avvisi su duplicati, interazioni o allergie: verificarli e confermare."
                )
        return cleaned


class TherapyStatusForm(forms.Form):
    status = forms.ChoiceField(label="Nuovo stato", choices=Therapy.Status.choices)
    reason = forms.CharField(label="Motivazione", max_length=255)


class AdministrationForm(forms.Form):
    status = forms.ChoiceField(choices=TherapyAdministration.Status.choices, initial=TherapyAdministration.Status.GIVEN)
    notes = forms.CharField(required=False, max_length=500)


class SOSAdministrationForm(forms.Form):
    therapy = forms.ModelChoiceField(label="Farmaco SOS", queryset=Therapy.objects.none())
    occurred_at = forms.DateTimeField(label="Ora somministrazione", widget=DateTimeInput(), initial=timezone.now)
    sos_reason = forms.CharField(label="Motivo della somministrazione", widget=forms.Textarea(attrs={"rows": 3}))
    dose_given = forms.CharField(label="Dose somministrata", required=False)
    notes = forms.CharField(label="Note", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    confirm_limits = forms.BooleanField(label="Confermo nonostante gli avvisi", required=False)

    def __init__(self, *args, guest=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_warnings = []
        self.fields["therapy"].queryset = Therapy.objects.filter(
            guest=guest, is_sos=True, status=Therapy.Status.ACTIVE
        ).select_related("drug")

    def clean(self):
        cleaned = super().clean()
        therapy = cleaned.get("therapy")
        if therapy:
            from .services import sos_limits_warnings

            self.limit_warnings = sos_limits_warnings(therapy, cleaned.get("occurred_at"))
            if self.limit_warnings and not cleaned.get("confirm_limits"):
                raise forms.ValidationError("Attenzione ai limiti di somministrazione SOS: confermare per procedere.")
        return cleaned


class SOSValidationForm(forms.Form):
    approve = forms.TypedChoiceField(
        label="Esito", choices=[("1", "Valida"), ("0", "Non validare")], coerce=lambda v: v == "1"
    )
    notes = forms.CharField(label="Note", required=False, widget=forms.Textarea(attrs={"rows": 2}))


class ParameterReadingForm(forms.ModelForm):
    class Meta:
        model = ParameterReading
        fields = ["parameter_type", "occurred_at", "value", "value_2", "notes"]
        widgets = {"occurred_at": DateTimeInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parameter_type"].queryset = ParameterType.objects.filter(active=True)

    def clean(self):
        cleaned = super().clean()
        ptype = cleaned.get("parameter_type")
        if ptype and ptype.kind == ParameterType.Kind.BLOOD_PRESSURE and cleaned.get("value_2") is None:
            self.add_error("value_2", "Indicare la pressione diastolica.")
        return cleaned


class QuickParametersForm(forms.Form):
    """Inserimento rapido di più parametri dello stesso ospite in una volta sola."""

    occurred_at = forms.DateTimeField(label="Data e ora rilevazione", widget=DateTimeInput(), initial=timezone.now)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.types = list(ParameterType.objects.filter(active=True))
        for ptype in self.types:
            self.fields[f"p_{ptype.pk}"] = forms.DecimalField(
                label=f"{ptype.name} ({ptype.unit})", required=False, decimal_places=2, max_digits=8
            )
            if ptype.kind == ParameterType.Kind.BLOOD_PRESSURE:
                self.fields[f"p_{ptype.pk}"].label = f"{ptype.name} – sistolica"
                self.fields[f"p2_{ptype.pk}"] = forms.DecimalField(
                    label=f"{ptype.name} – diastolica", required=False, decimal_places=2, max_digits=8
                )

    def readings(self):
        for ptype in self.types:
            value = self.cleaned_data.get(f"p_{ptype.pk}")
            if value is None:
                continue
            yield ptype, value, self.cleaned_data.get(f"p2_{ptype.pk}")


class ClinicalEventForm(forms.ModelForm):
    class Meta:
        model = ClinicalEvent
        fields = [
            "event_type", "severity", "occurred_at", "duration_minutes", "location", "description",
            "actions_taken", "injuries", "doctor_notified", "family_notified", "emergency_services_called",
        ]
        widgets = {
            "occurred_at": DateTimeInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
            "actions_taken": forms.Textarea(attrs={"rows": 2}),
            "injuries": forms.Textarea(attrs={"rows": 2}),
        }


class EmergencyForm(forms.ModelForm):
    """Modalità emergenza: pochi campi, compilabili in pochi secondi."""

    guest = forms.ModelChoiceField(label="Ospite", queryset=None)

    class Meta:
        model = ClinicalEvent
        fields = ["guest", "event_type", "description", "actions_taken", "emergency_services_called", "doctor_notified"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Cosa sta succedendo?"}),
            "actions_taken": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.guests.services import guests_in_care

        self.fields["guest"].queryset = guests_in_care()
        self.fields["event_type"].choices = [
            (ClinicalEvent.EventType.EMERGENCY, "Emergenza sanitaria"),
            (ClinicalEvent.EventType.SEIZURE, "Crisi epilettica"),
            (ClinicalEvent.EventType.AGITATION, "Crisi comportamentale"),
            (ClinicalEvent.EventType.FALL, "Caduta"),
            (ClinicalEvent.EventType.INCIDENT, "Incidente"),
            (ClinicalEvent.EventType.AGGRESSION, "Aggressione"),
            (ClinicalEvent.EventType.ELOPEMENT, "Allontanamento"),
        ]


class RestraintForm(forms.ModelForm):
    class Meta:
        model = Restraint
        fields = [
            "restraint_type", "occurred_at", "ended_at", "reason", "alternatives_tried", "authorized_by",
            "authorizing_doctor_name", "authorization_date", "authorization_document", "responsible_operator",
            "monitoring_notes",
        ]
        labels = {"occurred_at": "Inizio"}
        widgets = {
            "occurred_at": DateTimeInput(), "ended_at": DateTimeInput(), "authorization_date": DateInput(),
            "reason": forms.Textarea(attrs={"rows": 2}), "alternatives_tried": forms.Textarea(attrs={"rows": 2}),
            "monitoring_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, guest=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["authorized_by"].queryset = User.objects.filter(role=Role.DOCTOR, is_active=True)
        self.fields["responsible_operator"].queryset = User.objects.filter(is_active=True)
        if guest is not None:
            self.fields["authorization_document"].queryset = guest.documents.all()


class ParameterTypeForm(forms.ModelForm):
    class Meta:
        model = ParameterType
        fields = "__all__"
