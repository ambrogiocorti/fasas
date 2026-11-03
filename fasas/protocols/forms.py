from django import forms

from fasas.accounts.models import Role

from .models import Protocol, ProtocolActivation

# Parametri di ogni tipo di protocollo con i limiti ammessi: niente JSON da scrivere a mano.
# (chiave, etichetta, tipo, minimo, massimo, passo). I valori vanno comunque validati dal medico della struttura.
PARAM_FIELDS = {
    Protocol.Kind.EVACUATION: [("days", "Giorni senza evacuazione che attivano il protocollo", "int", 1, 10, 1)],
    Protocol.Kind.FEVER: [("threshold", "Temperatura che attiva il protocollo (°C)", "dec", 37, 41, "0.1"),
                          ("parameter", "Parametro da controllare", "param", None, None, None)],
    Protocol.Kind.GLYCEMIA: [("min", "Glicemia minima (mg/dL)", "int", 30, 150, 1),
                             ("max", "Glicemia massima (mg/dL)", "int", 100, 600, 1),
                             ("parameter", "Parametro da controllare", "param", None, None, None)],
    Protocol.Kind.SEIZURE: [("min_duration_minutes", "Durata minima della crisi (minuti, 0 = ogni crisi)", "int", 0, 60, 1)],
    Protocol.Kind.AGITATION: [("events", "Episodi di agitazione", "int", 1, 20, 1),
                              ("window_hours", "Nell'arco di (ore)", "int", 1, 168, 1)],
    Protocol.Kind.SOS: [("count", "Somministrazioni SOS", "int", 1, 20, 1),
                        ("window_hours", "Nell'arco di (ore)", "int", 1, 168, 1)],
}


def _param_name(kind, key):
    return f"p_{kind}_{key}"


class ProtocolForm(forms.ModelForm):
    notify_roles = forms.MultipleChoiceField(
        label="Ruoli da avvisare", choices=Role.choices, required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Protocol
        fields = ["name", "kind", "description", "actions", "severity", "applies_to_all", "tags", "guests",
                  "notify_roles", "active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "actions": forms.Textarea(attrs={"rows": 4}),
            "tags": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.clinical.models import ParameterType
        from fasas.guests.services import guests_in_care

        self.fields["guests"].queryset = guests_in_care()
        self.params_changed = False
        current = dict(self.instance.params or {}) if self.instance.pk else {}
        current_kind = self.instance.kind or self.initial.get("kind")
        parameter_choices = [(p.code, f"{p.name} ({p.unit})") for p in ParameterType.objects.filter(active=True)]
        kind_labels = dict(Protocol.Kind.choices)
        # un gruppo di campi per tipo: la pagina mostra solo quelli del tipo scelto (fasas.js), senza JS si vedono tutti
        for kind, specs in PARAM_FIELDS.items():
            defaults = Protocol.DEFAULT_PARAMS.get(kind, {})
            for key, label, kind_of, low, high, step in specs:
                value = current.get(key, defaults.get(key)) if kind == current_kind else defaults.get(key)
                attrs = {"data-protocol-kind": kind}
                if kind_of == "param":
                    field = forms.ChoiceField(choices=parameter_choices, required=False, initial=value,
                                              widget=forms.Select(attrs=attrs))
                elif kind_of == "dec":
                    field = forms.DecimalField(min_value=low, max_value=high, decimal_places=1, required=False,
                                               initial=value, widget=forms.NumberInput(attrs={**attrs, "step": step}))
                else:
                    field = forms.IntegerField(min_value=low, max_value=high, required=False, initial=value,
                                               widget=forms.NumberInput(attrs={**attrs, "step": step}))
                field.label = f"{label} – {kind_labels[kind]}"
                self.fields[_param_name(kind, key)] = field

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        if not kind:
            return cleaned
        params = {}
        for key, _label, kind_of, *_ in PARAM_FIELDS.get(kind, []):
            name = _param_name(kind, key)
            value = cleaned.get(name)
            if value in (None, ""):
                self.add_error(name, "Valore obbligatorio per questo tipo di protocollo.")
                continue
            params[key] = float(value) if kind_of == "dec" else value
        if kind == Protocol.Kind.GLYCEMIA and params.get("min") is not None and params.get("max") is not None \
                and params["min"] >= params["max"]:
            self.add_error(_param_name(kind, "max"), "La glicemia massima deve superare la minima.")
        old = dict(self.instance.params or {}) if self.instance.pk else {}
        self.params_changed = bool(self.instance.pk) and (params != old or kind != self.instance.kind)
        self.instance.params = params
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
