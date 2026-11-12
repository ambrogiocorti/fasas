from django import forms

from fasas.guests.forms import DateInput

from .models import Document
from .services import validate_upload


class UploadField(forms.FileField):
    def validate(self, value):
        super().validate(value)
        if value:
            validate_upload(value)


class DocumentForm(forms.ModelForm):
    file = UploadField(label="File")

    class Meta:
        model = Document
        fields = ["category", "title", "description", "document_date", "expires_on"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "document_date": DateInput(),
            "expires_on": DateInput(),
        }


class DocumentEditForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["category", "title", "description", "document_date", "expires_on"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "document_date": DateInput(),
            "expires_on": DateInput(),
        }


class VersionForm(forms.Form):
    file = UploadField(label="Nuova versione del file")
    note = forms.CharField(label="Nota di versione", required=False, max_length=255)
