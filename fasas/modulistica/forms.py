from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils.text import slugify

from fasas.accounts.models import Role

from .models import FormField, FormSettings, FormTemplate

REPRESENTATIVE = ["Ospite", "Tutore", "Amministratore di sostegno", "Familiare di riferimento", "Altro"]


def fill_form_class(fields, respondent=False):
    """Modulo da compilare online, costruito dai campi della fotografia del modulo."""
    attrs = {}
    if respondent:
        attrs["respondent"] = forms.CharField(label="Nome e cognome di chi risponde", max_length=200)
        attrs["respondent_role"] = forms.ChoiceField(label="In qualità di", choices=[(r, r) for r in REPRESENTATIVE])
    for field in fields:
        kind, label, required = field["kind"], field["label"], field.get("required", False)
        help_text = field.get("help_text", "")
        choices = [(o, o) for o in field.get("options") or []]
        if kind == "section":
            continue
        if kind == "text":
            attrs[field["key"]] = forms.CharField(label=label, required=required, max_length=500, help_text=help_text)
        elif kind == "textarea":
            attrs[field["key"]] = forms.CharField(label=label, required=required, max_length=4000, help_text=help_text,
                                                  widget=forms.Textarea(attrs={"rows": 3}))
        elif kind == "date":
            attrs[field["key"]] = forms.DateField(label=label, required=required, help_text=help_text,
                                                  widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
        elif kind == "choice":
            attrs[field["key"]] = forms.ChoiceField(label=label, required=required, choices=choices,
                                                    help_text=help_text, widget=forms.RadioSelect)
        elif kind == "multi":
            attrs[field["key"]] = forms.MultipleChoiceField(label=label, required=required, choices=choices,
                                                            help_text=help_text, widget=forms.CheckboxSelectMultiple)
        elif kind == "check":
            attrs[field["key"]] = forms.BooleanField(label=label, required=required, help_text=help_text)
    return type("FillForm", (forms.Form,), attrs)


def answers_from(form, fields):
    values = {}
    for field in fields:
        if field["kind"] == "section":
            continue
        value = form.cleaned_data.get(field["key"])
        values[field["key"]] = value.isoformat() if hasattr(value, "isoformat") else value
    return values


class SettingsForm(forms.ModelForm):
    class Meta:
        model = FormSettings
        fields = ["holder", "address", "contacts", "dpo", "dpo_contacts"]


class TemplateForm(forms.ModelForm):
    staff_roles = forms.MultipleChoiceField(
        label="Ruoli del personale", required=False, widget=forms.CheckboxSelectMultiple,
        choices=[(r.value, r.label) for r in Role if r != Role.FAMILY])
    signatures_text = forms.CharField(
        label="Righe per le firme (una per riga)", required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Es. «L'ospite o chi lo rappresenta», «Per la struttura». Vuoto: nessuna riga per la firma.")
    document_category = forms.ChoiceField(label="Categoria nel fascicolo dell'ospite")

    class Meta:
        model = FormTemplate
        fields = ["title", "intro", "for_guests", "for_family", "for_staff", "staff_roles", "auto_assign",
                  "requires_signature", "withdrawable", "document_category", "order"]
        widgets = {"intro": forms.Textarea(attrs={"rows": 14})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.documents.models import Document

        self.fields["document_category"].choices = [(c.value, c.label) for c in Document.Category
                                                    if c.value in ("form", "legal", "consent", "other")]
        self.fields["signatures_text"].initial = "\n".join(self.instance.signatures or [])

    def clean(self):
        data = super().clean()
        if not (data.get("for_guests") or data.get("for_family") or data.get("for_staff")):
            raise forms.ValidationError("Indicare almeno a chi è destinato il modulo.")
        if data.get("for_staff") and not data.get("staff_roles"):
            self.add_error("staff_roles", "Indicare i ruoli del personale.")
        return data

    def save(self, commit=True):
        self.instance.signatures = [line.strip() for line in self.cleaned_data["signatures_text"].splitlines()
                                    if line.strip()][:6]
        return super().save(commit)


class FieldForm(forms.ModelForm):
    options_text = forms.CharField(label="Opzioni (una per riga)", required=False,
                                   widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = FormField
        fields = ["order", "label", "kind", "required", "help_text"]
        widgets = {"order": forms.NumberInput(attrs={"style": "width:5em"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["options_text"].initial = "\n".join(self.instance.options or [])
        self.fields["order"].required = False

    def has_changed(self):
        # una riga nuova senza domanda è una riga vuota, qualunque cosa riporti negli altri campi
        if not self.instance.pk and not (self.data.get(self.add_prefix("label")) or "").strip():
            return False
        return super().has_changed()

    def clean(self):
        data = super().clean()
        if data.get("order") is None:
            data["order"] = 0
        options = [o.strip() for o in (data.get("options_text") or "").splitlines() if o.strip()]
        if data.get("kind") in ("choice", "multi") and len(options) < 2 and not data.get("DELETE"):
            self.add_error("options_text", "Servono almeno due opzioni.")
        data["options"] = options
        return data

    def save(self, commit=True):
        field = super().save(commit=False)
        field.options = self.cleaned_data.get("options", [])
        if not field.key:
            base = slugify(field.label)[:30].replace("-", "_") or "campo"
            key, n = base, 2
            while FormField.objects.filter(template=field.template, key=key).exclude(pk=field.pk).exists():
                key, n = f"{base}_{n}", n + 1
            field.key = key
        if commit:
            field.save()
        return field


class BaseFieldFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        number = (index + 1) if index is not None else ""
        for name, field in form.fields.items():  # in tabella le etichette non si vedono: le leggono i lettori di schermo
            label = "Elimina" if name == "DELETE" else str(field.label)
            field.widget.attrs.setdefault("aria-label", f"{label} – riga {number}")


FieldFormSet = inlineformset_factory(FormTemplate, FormField, form=FieldForm, formset=BaseFieldFormSet, extra=2,
                                     can_delete=True)


class DistributeForm(forms.Form):
    roles = forms.MultipleChoiceField(label="Ruoli", widget=forms.CheckboxSelectMultiple,
                                      choices=[(r.value, r.label) for r in Role if r != Role.FAMILY])
    due_date = forms.DateField(label="Da compilare entro il", required=False,
                               widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class SignedForm(forms.Form):
    file = forms.FileField(label="Scansione o foto del modulo firmato (PDF, JPEG o PNG)",
                           widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf",
                                                                  "capture": "environment"}))


class WithdrawForm(forms.Form):
    reason = forms.CharField(label="Motivo o chi ha chiesto la revoca", max_length=255)
