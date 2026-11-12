import datetime

from django import forms

from .models import AdmissionEvent, Allergy, ClinicalTag, Diagnosis, Guest, GuestContact


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(**kwargs)


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%dT%H:%M")
        super().__init__(**kwargs)


class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = [
            "last_name", "first_name", "sex", "birth_date", "birth_place", "fiscal_code", "health_card_number",
            "residence_address", "residence_city", "residence_zip", "room", "admission_date",
            "general_practitioner", "general_practitioner_phone", "general_practitioner_email", "referring_service",
            "disability_description", "disability_certifications", "diet", "diet_texture", "clinical_notes", "tags",
        ]
        widgets = {
            "birth_date": DateInput(),
            "admission_date": DateInput(),
            "tags": forms.CheckboxSelectMultiple,
            "disability_description": forms.Textarea(attrs={"rows": 3}),
            "clinical_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_fiscal_code(self):
        return self.cleaned_data["fiscal_code"].upper().strip()

    def clean_birth_date(self):
        value = self.cleaned_data["birth_date"]
        if value > datetime.date.today():
            raise forms.ValidationError("La data di nascita non può essere futura.")
        return value


class GuestContactForm(forms.ModelForm):
    class Meta:
        model = GuestContact
        exclude = ["guest"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class DiagnosisForm(forms.ModelForm):
    class Meta:
        model = Diagnosis
        exclude = ["guest"]
        widgets = {"diagnosed_on": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}


class AllergyForm(forms.ModelForm):
    class Meta:
        model = Allergy
        exclude = ["guest"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class ClinicalTagForm(forms.ModelForm):
    escalate_event_types = forms.MultipleChoiceField(
        label="Eventi da segnalare con priorità critica", required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = ClinicalTag
        fields = ["name", "color", "description", "alert_message", "escalate_event_types", "order"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"}), "description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.clinical.models import ClinicalEvent

        self.fields["escalate_event_types"].choices = ClinicalEvent.EventType.choices


class DischargeForm(forms.Form):
    date = forms.DateField(label="Data dimissione", initial=datetime.date.today, widget=DateInput())
    reason = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))
    destination = forms.CharField(label="Destinazione (struttura, domicilio...)", required=False)
    confirm = forms.BooleanField(
        label="Confermo: la cartella sarà archiviata e non sarà più modificabile", required=True
    )


class MovementForm(forms.ModelForm):
    class Meta:
        model = AdmissionEvent
        fields = ["kind", "date", "notes"]
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [
            c for c in AdmissionEvent.Kind.choices if c[0] not in (AdmissionEvent.Kind.ADMISSION, AdmissionEvent.Kind.DISCHARGE)
        ]
