import datetime

from django import forms
from django.utils import timezone

from fasas.guests.forms import DateInput
from fasas.guests.models import Guest

from .models import ReportFormat, ReportSchedule, ReportType


class GenerateReportForm(forms.Form):
    report_type = forms.ChoiceField(label="Contenuto", choices=ReportType.choices)
    format = forms.ChoiceField(label="Formato", choices=ReportFormat.choices)
    start = forms.DateField(label="Dal", widget=DateInput())
    end = forms.DateField(label="Al", widget=DateInput())
    guest = forms.ModelChoiceField(label="Ospite (vuoto = tutti)", queryset=Guest.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["start"].initial = today.replace(day=1)
        self.fields["end"].initial = today

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end:
            if end < start:
                raise forms.ValidationError("La data finale precede quella iniziale.")
            if (end - start) > datetime.timedelta(days=366 * 5):
                raise forms.ValidationError("Il periodo massimo è di 5 anni.")
        return cleaned


class ReportScheduleForm(forms.ModelForm):
    class Meta:
        model = ReportSchedule
        fields = "__all__"


class GuestExportForm(forms.Form):
    include_documents = forms.BooleanField(label="Includi i documenti allegati (PDF e immagini)", required=False,
                                           initial=True)
    date_from = forms.DateField(label="Dati a partire dal (vuoto = tutto lo storico)", required=False,
                                widget=DateInput())
