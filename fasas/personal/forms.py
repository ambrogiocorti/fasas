from django import forms

from .models import CashMovement, PersonalItem


class MovementForm(forms.Form):
    kind = forms.ChoiceField(label="Tipo", choices=CashMovement.Kind.choices)
    amount = forms.DecimalField(label="Importo (€)", min_value=0.01, max_digits=9, decimal_places=2)
    occurred_on = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    description = forms.CharField(label="Descrizione", max_length=255)
    counterpart = forms.CharField(label="Da / a chi", max_length=120, required=False,
                                  help_text="Es. nome del familiare che versa, negozio.")
    receipt = forms.FileField(label="Scontrino (foto o PDF, facoltativo)", required=False,
                              widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf",
                                                                     "capture": "environment"}))


class VoidForm(forms.Form):
    reason = forms.CharField(label="Motivo dell'annullamento", max_length=255)


class ItemForm(forms.ModelForm):
    class Meta:
        model = PersonalItem
        fields = ["name", "description", "quantity", "value", "received_on", "received_from", "status",
                  "status_date", "notes"]
        widgets = {
            "received_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "status_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class PeriodForm(forms.Form):
    start = forms.DateField(label="Dal", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    end = forms.DateField(label="Al", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] < cleaned["start"]:
            raise forms.ValidationError("La fine del periodo precede l'inizio.")
        return cleaned
