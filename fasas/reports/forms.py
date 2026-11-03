import datetime

from django import forms
from django.utils import timezone

from fasas.guests.forms import DateInput
from fasas.guests.models import Guest

from .models import FORMAT_CHOICES, ReportSchedule, ReportTemplate, ReportType


class GenerateReportForm(forms.Form):
    report_type = forms.ChoiceField(label="Contenuto", choices=[("", "— scegliere —")] + ReportType.choices,
                                    required=False)
    template = forms.ModelChoiceField(label="oppure modello di report", queryset=ReportTemplate.objects.all(),
                                      required=False, help_text="Più sezioni con le colonne scelte.")
    format = forms.ChoiceField(label="Formato", choices=FORMAT_CHOICES)
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
        if not cleaned.get("report_type") and not cleaned.get("template"):
            raise forms.ValidationError("Scegliere il contenuto oppure un modello di report.")
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
        fields = ["name", "report_type", "template", "format", "frequency", "interval_days", "guest",
                  "retention_years", "active"]

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("report_type") and not cleaned.get("template"):
            self.add_error(None, "Scegliere il contenuto oppure un modello di report.")
        if cleaned.get("frequency") == ReportSchedule.Frequency.INTERVAL and not cleaned.get("interval_days"):
            self.add_error("interval_days", "Indicare ogni quanti giorni.")
        return cleaned


class ReportTemplateForm(forms.ModelForm):
    """Per ogni contenuto: incluso o no, posizione nel report, colonne da mostrare."""

    class Meta:
        model = ReportTemplate
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .generators import columns_for

        current = {section["type"]: (index, section) for index, section in enumerate(self.instance.sections or [])}
        for code, label in ReportType.choices:
            columns = columns_for(code)
            index, section = current.get(code, (None, None))
            self.fields[f"include_{code}"] = forms.BooleanField(
                label=f"{label}: includi", required=False, initial=section is not None)
            self.fields[f"order_{code}"] = forms.IntegerField(
                label=f"{label}: posizione nel report", min_value=1, max_value=len(ReportType.choices), required=False,
                initial=(index + 1) if index is not None else None)
            self.fields[f"columns_{code}"] = forms.MultipleChoiceField(
                label=f"{label}: colonne", choices=[(c, c) for c in columns], required=False,
                widget=forms.CheckboxSelectMultiple,
                initial=(section.get("columns") if section else columns))

    def clean(self):
        cleaned = super().clean()
        chosen = []
        for position, (code, _label) in enumerate(ReportType.choices):
            if not cleaned.get(f"include_{code}"):
                continue
            columns = cleaned.get(f"columns_{code}") or []
            if not columns:
                self.add_error(f"columns_{code}", "Scegliere almeno una colonna.")
            order = cleaned.get(f"order_{code}") or (100 + position)
            chosen.append((order, position, {"type": code, "columns": columns}))
        if not chosen:
            raise forms.ValidationError("Includere almeno una sezione.")
        self.instance.sections = [section for _, _, section in sorted(chosen)]
        return cleaned


class GuestExportForm(forms.Form):
    include_documents = forms.BooleanField(label="Includi i documenti allegati (PDF e immagini)", required=False,
                                           initial=True)
    date_from = forms.DateField(label="Dati a partire dal (vuoto = tutto lo storico)", required=False,
                                widget=DateInput())
