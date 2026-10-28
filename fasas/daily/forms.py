from django import forms
from django.utils import timezone

from fasas.accounts.models import User
from fasas.guests.forms import DateInput, DateTimeInput

from .models import ChecklistItem, ChecklistTemplate, DailyRecord, DiaryEntry, EvacuationRecord, ShiftAssignment


class DailyRecordForm(forms.ModelForm):
    class Meta:
        model = DailyRecord
        fields = ["category", "occurred_at", "meal", "intake", "description"]
        widgets = {"occurred_at": DateTimeInput(), "description": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("category") == DailyRecord.Category.MEAL and not cleaned.get("meal"):
            self.add_error("meal", "Indicare il pasto.")
        if cleaned.get("category") != DailyRecord.Category.MEAL and not cleaned.get("description"):
            self.add_error("description", "Inserire una descrizione.")
        return cleaned


class ShiftDailyRecordForm(DailyRecordForm):
    """Inserimento dal registro del turno: si sceglie anche l'ospite."""

    guest = forms.ModelChoiceField(label="Ospite", queryset=None)

    class Meta(DailyRecordForm.Meta):
        fields = ["guest"] + DailyRecordForm.Meta.fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.guests.services import guests_in_care

        self.fields["guest"].queryset = guests_in_care()


class EvacuationForm(forms.ModelForm):
    class Meta:
        model = EvacuationRecord
        fields = ["occurred_at", "outcome", "consistency", "amount", "assisted", "notes"]
        widgets = {"occurred_at": DateTimeInput()}


class DiaryEntryForm(forms.ModelForm):
    class Meta:
        model = DiaryEntry
        fields = ["occurred_at", "text", "is_relevant"]
        widgets = {
            "occurred_at": DateTimeInput(),
            "text": forms.Textarea(attrs={"rows": 5, "placeholder": "Es. Ospite agitato durante il pranzo. "
                                                                    "Intervenuto operatore. Situazione rientrata."}),
        }


class ShiftAssignmentForm(forms.ModelForm):
    class Meta:
        model = ShiftAssignment
        fields = ["date", "shift", "user", "is_shift_lead", "notes"]
        widgets = {"date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(is_active=True)


class CloseShiftForm(forms.Form):
    handover_notes = forms.CharField(
        label="Consegne per il turno successivo", required=False, widget=forms.Textarea(attrs={"rows": 4})
    )
    confirm = forms.BooleanField(label="Confermo la chiusura: i dati del turno non saranno più modificabili")


class ReopenShiftForm(forms.Form):
    reason = forms.CharField(label="Motivo della riapertura straordinaria", widget=forms.Textarea(attrs={"rows": 3}))


class ChecklistTemplateForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = "__all__"


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = "__all__"
        widgets = {"required_tags": forms.CheckboxSelectMultiple}


def now_local():
    return timezone.localtime()
