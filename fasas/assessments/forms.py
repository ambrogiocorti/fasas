from django import forms
from django.utils import timezone

from fasas.guests.forms import DateTimeInput


class AssessmentForm(forms.Form):
    """Una domanda a scelta singola per ogni voce della scala, con i punteggi della scheda."""

    occurred_at = forms.DateTimeField(label="Data e ora della valutazione", widget=DateTimeInput())
    notes = forms.CharField(label="Note", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, scale, **kwargs):
        super().__init__(*args, **kwargs)
        self.scale = scale
        self.fields["occurred_at"].initial = timezone.localtime()
        for item in scale.items:
            self.fields[f"item_{item.key}"] = forms.TypedChoiceField(
                label=item.label, coerce=int, widget=forms.RadioSelect, help_text=item.hint,
                choices=[(points, label) for points, label in item.options])
        self.order_fields([f"item_{item.key}" for item in scale.items] + ["occurred_at", "notes"])

    def answers(self):
        return {item.key: self.cleaned_data[f"item_{item.key}"] for item in self.scale.items}
