from django import forms
from django.utils import timezone

from fasas.guests.forms import DateInput, DateTimeInput

from .models import DressingPlan, Wound, WoundCheck

CHECK_FIELDS = ["stage", "length_cm", "width_cm", "depth_cm", "bed", "exudate", "periwound", "odour",
                "infection_signs", "pain", "notes"]


class PhotoInput(forms.ClearableFileInput):
    """Sul telefono apre direttamente la fotocamera posteriore."""

    def __init__(self, attrs=None):
        super().__init__({"accept": "image/jpeg,image/png", "capture": "environment", **(attrs or {})})


class _WoundFormBase(forms.ModelForm):
    """Data, foto e controlli comuni alla nuova lesione e alle rilevazioni successive."""

    occurred_at = forms.DateTimeField(label="Data e ora della rilevazione", widget=DateTimeInput())
    photo = forms.FileField(label="Foto (facoltativa)", required=False, widget=PhotoInput(),
                            help_text="Solo con il dispositivo della struttura. La foto è cifrata come i documenti "
                                      "e salvata senza posizione GPS.")

    def _setup_widgets(self):
        self.fields["occurred_at"].initial = timezone.localtime()
        self.fields["pain"].widget.attrs.update({"min": 0, "max": 10})
        for name in ("length_cm", "width_cm", "depth_cm"):
            self.fields[name].widget.attrs.update({"min": 0, "max": 99, "step": "0.1"})
        for name in ("notes", "description"):
            if name in self.fields:
                self.fields[name].widget.attrs["rows"] = 3

    def clean_pain(self):
        pain = self.cleaned_data.get("pain")
        if pain is not None and pain > 10:
            raise forms.ValidationError("Il dolore va da 0 a 10.")
        return pain

    def clean(self):
        cleaned = super().clean()
        for name in ("length_cm", "width_cm", "depth_cm"):
            value = cleaned.get(name)
            if value is not None and value < 0:
                self.add_error(name, "Valore non valido.")
        return cleaned


class WoundCheckForm(_WoundFormBase):
    class Meta:
        model = WoundCheck
        fields = CHECK_FIELDS

    def __init__(self, *args, wound=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_widgets()
        if wound is not None and wound.kind != Wound.Kind.PRESSURE:
            del self.fields["stage"]
        self.order_fields(["occurred_at"] + CHECK_FIELDS + ["photo"])

    def check_data(self):
        return {name: self.cleaned_data[name] for name in CHECK_FIELDS if name in self.cleaned_data}


class WoundForm(_WoundFormBase):
    """Nuova lesione con la prima rilevazione (misure, fondo, foto) nella stessa pagina."""

    class Meta:
        model = Wound
        fields = ["kind", "site", "side", "site_detail", "origin", "stage", "description", "check_interval_days"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["occurred_at"].label = "Osservata il"
        for name, field in forms.models.fields_for_model(WoundCheck, fields=CHECK_FIELDS[1:]).items():
            field.required = False
            self.fields[name] = field
        self._setup_widgets()
        self.fields["check_interval_days"].widget.attrs.update({"min": 0, "max": 60})
        self.order_fields(["occurred_at", "kind", "site", "side", "site_detail", "origin", "stage", "description"]
                          + CHECK_FIELDS[1:] + ["photo", "check_interval_days"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == Wound.Kind.PRESSURE and not cleaned.get("stage"):
            self.add_error("stage", "Indicare la categoria della lesione da pressione.")
        interval = cleaned.get("check_interval_days")
        if interval is not None and interval > 60:
            self.add_error("check_interval_days", "Al massimo 60 giorni.")
        return cleaned

    def wound_data(self):
        return {name: self.cleaned_data[name] for name in self._meta.fields}

    def check_data(self):
        data = {name: self.cleaned_data.get(name) for name in CHECK_FIELDS[1:]}
        data["stage"] = self.cleaned_data.get("stage", "")
        meaningful = [v for k, v in data.items() if k not in ("stage", "odour", "infection_signs") and v not in (None, "")]
        return data if (meaningful or data["odour"] or data["infection_signs"]) else None


class DressingPlanForm(forms.ModelForm):
    class Meta:
        model = DressingPlan
        fields = ["products", "procedure", "interval_days", "start_date", "indicated_by"]
        widgets = {"start_date": DateInput(), "products": forms.Textarea(attrs={"rows": 3}),
                   "procedure": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].initial = timezone.localdate()
        self.fields["interval_days"].widget.attrs.update({"min": 1, "max": 60})

    def clean_interval_days(self):
        value = self.cleaned_data["interval_days"]
        if not 1 <= value <= 60:
            raise forms.ValidationError("Tra 1 e 60 giorni.")
        return value


class DressingForm(forms.Form):
    occurred_at = forms.DateTimeField(label="Data e ora", widget=DateTimeInput())
    products_used = forms.CharField(label="Prodotti usati (vuoto = quelli del piano)", required=False,
                                    max_length=255)
    notes = forms.CharField(label="Note", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["occurred_at"].initial = timezone.localtime()


class CloseWoundForm(forms.Form):
    status = forms.ChoiceField(label="Esito", choices=[(Wound.Status.HEALED, "Guarita"),
                                                       (Wound.Status.CLOSED, "Chiusa per altro motivo")])
    closed_at = forms.DateTimeField(label="Data e ora", widget=DateTimeInput())
    note = forms.CharField(label="Nota (obbligatoria se chiusa per altro motivo)", required=False,
                           widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["closed_at"].initial = timezone.localtime()
