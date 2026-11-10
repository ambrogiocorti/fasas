from django import forms

from fasas.core.shifts import Shift

from .models import CareTask, CareTaskCheck, parse_time


class CareTaskForm(forms.ModelForm):
    times_text = forms.CharField(label="Orari fissi", required=False,
                                 help_text="Orari HH:MM separati da virgola (es. 10:00, 15:00, 21:00). "
                                           "Oppure lasciare vuoto e indicare «ogni quante ore».")
    shifts = forms.MultipleChoiceField(label="Solo in questi turni", choices=Shift.choices, required=False,
                                       widget=forms.CheckboxSelectMultiple,
                                       help_text="Nessuna scelta = in tutti i turni.")

    class Meta:
        model = CareTask
        fields = ["kind", "label", "instructions", "times_text", "every_hours", "first_time", "shifts",
                  "late_minutes", "start_date", "end_date"]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "first_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["times_text"].initial = ", ".join(self.instance.times or [])
            self.fields["shifts"].initial = self.instance.shifts or []

    def clean_times_text(self):
        values = [v.strip() for v in self.cleaned_data["times_text"].replace(";", ",").split(",") if v.strip()]
        return sorted({parse_time(v).strftime("%H:%M") for v in values})

    def clean(self):
        cleaned = super().clean()
        self.instance.times = cleaned.get("times_text") or []
        self.instance.shifts = cleaned.get("shifts") or []
        return cleaned


class CheckForm(forms.Form):
    status = forms.ChoiceField(label="Esito", choices=CareTaskCheck.Status.choices)
    notes = forms.CharField(label="Note", required=False, max_length=500,
                            help_text="Obbligatorie se non è stata fatta o è stata rifiutata.")


class EndTaskForm(forms.Form):
    reason = forms.CharField(label="Motivo della fine", max_length=255)
