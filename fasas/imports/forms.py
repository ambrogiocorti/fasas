from django import forms

from fasas.documents.models import Document
from fasas.guests.forms import DateInput

MAX_WORKBOOK_MB = 15


class WorkbookForm(forms.Form):
    file = forms.FileField(label="File Excel compilato", help_text="Il modello scaricato da questa pagina, in formato .xlsx")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if not uploaded.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Caricare un file .xlsx (salvare dal programma con «Cartella di lavoro Excel»).")
        if uploaded.size > MAX_WORKBOOK_MB * 1024 * 1024:
            raise forms.ValidationError(f"Il file supera {MAX_WORKBOOK_MB} MB.")
        return uploaded


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            return [super(MultipleFileField, self).clean(item, initial) for item in data]
        return [super().clean(data, initial)]


class DocumentsForm(forms.Form):
    files = MultipleFileField(
        label="File scansionati o archivio ZIP",
        help_text="Nel nome del file o della cartella indicare il codice fiscale oppure «Cognome Nome» dell'ospite",
    )
    category = forms.ChoiceField(label="Categoria", choices=Document.Category.choices, initial=Document.Category.OTHER)
    document_date = forms.DateField(label="Data dei documenti", required=False, widget=DateInput(),
                                    help_text="Facoltativa, vale per tutti i file del caricamento")
