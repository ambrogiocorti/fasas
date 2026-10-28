import json

from django import forms

from fasas.accounts.models import Role

from .models import Protocol, ProtocolActivation


class ProtocolForm(forms.ModelForm):
    params = forms.CharField(
        label="Parametri della regola (JSON)", widget=forms.Textarea(attrs={"rows": 3, "class": "mono"}), required=False,
    )
    notify_roles = forms.MultipleChoiceField(
        label="Ruoli da avvisare", choices=Role.choices, required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Protocol
        fields = ["name", "kind", "description", "params", "actions", "severity", "applies_to_all", "tags", "guests",
                  "notify_roles", "validated_by", "active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "actions": forms.Textarea(attrs={"rows": 4}),
            "tags": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kind = self.instance.kind or self.initial.get("kind")
        if self.instance.pk:
            self.initial["params"] = json.dumps(self.instance.params or {}, ensure_ascii=False)
        elif kind:
            self.initial.setdefault("params", json.dumps(Protocol.DEFAULT_PARAMS.get(kind, {})))
        self.fields["params"].help_text = " · ".join(str(v) for v in Protocol.PARAM_HELP.values())
        from fasas.guests.services import guests_in_care

        self.fields["guests"].queryset = guests_in_care()

    def clean_params(self):
        raw = self.cleaned_data.get("params") or "{}"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"JSON non valido: {exc}") from None
        if not isinstance(value, dict):
            raise forms.ValidationError("I parametri devono essere un oggetto JSON, es. {\"days\": 3}.")
        return value

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        params = cleaned.get("params") or {}
        if kind:
            merged = {**Protocol.DEFAULT_PARAMS.get(kind, {}), **params}
            cleaned["params"] = merged
        return cleaned


class ActionDoneForm(forms.Form):
    action_label = forms.CharField(widget=forms.HiddenInput)
    notes = forms.CharField(label="Esito / note", required=False, max_length=255)


class ResolveForm(forms.Form):
    status = forms.ChoiceField(label="Chiusura", choices=[
        (ProtocolActivation.Status.RESOLVED, "Risolto"),
        (ProtocolActivation.Status.DISMISSED, "Archivia (attivazione non necessaria)"),
    ])
    notes = forms.CharField(label="Esito", widget=forms.Textarea(attrs={"rows": 3}))
