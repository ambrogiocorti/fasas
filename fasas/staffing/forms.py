from django import forms
from django.forms import modelformset_factory
from django.utils import timezone

from fasas.accounts.models import User
from fasas.guests.forms import DateInput

from .models import Code, LeaveRequest, RotaSettings, ShiftChange, StaffProfile


class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["kind", "start", "end", "note"]
        widgets = {"start": DateInput(), "end": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [c for c in LeaveRequest.Kind.choices if c[0] != LeaveRequest.Kind.SICK]

    def clean(self):
        data = super().clean()
        if data.get("start") and data["start"] < timezone.localdate():
            self.add_error("start", "Le richieste si fanno per giorni futuri; per le assenze passate avvisare il coordinatore.")
        return data


class ShiftChangeForm(forms.Form):
    kind = forms.ChoiceField(label="Tipo", choices=ShiftChange.Kind.choices)
    date = forms.DateField(label="Giorno", widget=DateInput())
    colleague = forms.ModelChoiceField(label="Collega", queryset=User.objects.none())
    note = forms.CharField(label="Motivo", required=False, max_length=255)

    def __init__(self, *args, user=None, colleagues=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["colleague"].queryset = User.objects.filter(pk__in=[c.pk for c in colleagues]).exclude(
            pk=getattr(user, "pk", None)).order_by("last_name")


class DecisionForm(forms.Form):
    note = forms.CharField(label="Nota", required=False, max_length=255)


class RotaSettingsForm(forms.ModelForm):
    class Meta:
        model = RotaSettings
        exclude = ["community"]


StaffProfileFormSet = modelformset_factory(
    StaffProfile, fields=["in_rota", "weekly_hours", "can_lead", "no_nights", "order"], extra=0)

PAINT_CODES = [("", "Vuoto")] + list(Code.choices)
