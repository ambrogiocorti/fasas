from django import forms
from django.utils import timezone

from fasas.guests.forms import DateInput

from .models import AttendanceStatus, BillingSettings, FeePayment, GuestFeeLine


class CorrectionForm(forms.Form):
    date = forms.DateField(label="Giorno", widget=DateInput())
    status = forms.ChoiceField(label="Presenza", choices=AttendanceStatus.choices)
    reason = forms.CharField(label="Motivo della correzione", max_length=255,
                             help_text="Es. rientro in famiglia non registrato nei movimenti")


class CloseMonthForm(forms.Form):
    notes = forms.CharField(label="Note per la rendicontazione", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    confirm = forms.BooleanField(label="Ho controllato le presenze del mese: dopo la chiusura non si possono più modificare")


class ReasonForm(forms.Form):
    reason = forms.CharField(label="Motivo", max_length=255)


class FeeLineForm(forms.ModelForm):
    class Meta:
        model = GuestFeeLine
        fields = ["description", "payer", "payer_name", "payer_tax_code", "payer_address", "payer_email", "daily_rate",
                  "hospital_percent", "family_percent", "absent_percent", "max_absence_days", "valid_from", "valid_to",
                  "notes"]
        widgets = {"valid_from": DateInput(), "valid_to": DateInput()}

    def clean(self):
        data = super().clean()
        if data.get("valid_to") and data.get("valid_from") and data["valid_to"] < data["valid_from"]:
            self.add_error("valid_to", "La fine precede l'inizio.")
        return data


class PaymentForm(forms.ModelForm):
    class Meta:
        model = FeePayment
        fields = ["date", "amount", "method", "reference"]
        widgets = {"date": DateInput()}

    def __init__(self, *args, statement=None, **kwargs):
        super().__init__(*args, **kwargs)
        if statement is not None and not self.is_bound:
            self.initial.setdefault("amount", statement.balance)
            self.initial.setdefault("date", timezone.localdate())


class SettingsForm(forms.ModelForm):
    class Meta:
        model = BillingSettings
        exclude = ["community"]
        widgets = {"statement_notes": forms.Textarea(attrs={"rows": 3})}
