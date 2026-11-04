from django import forms

from fasas.guests.forms import DateInput

from .models import Drug, DrugInteraction, StockLot, StockMovement


class DrugForm(forms.ModelForm):
    official_lookup = forms.CharField(
        label="Cerca nell'elenco ufficiale AIFA", required=False,
        help_text="Nome, principio attivo o codice AIC (anche col lettore di codici a barre): scegliendo una confezione "
                  "si compilano nome, principio attivo, ATC e AIC. Si può sempre scrivere a mano.")

    class Meta:
        model = Drug
        fields = "__all__"
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        from django.urls import reverse

        from .models import OfficialPackage

        super().__init__(*args, **kwargs)
        if OfficialPackage.objects.exists():
            self.fields["official_lookup"].widget.attrs.update({
                "data-official-search": reverse("pharmacy:official_search"), "autocomplete": "off",
                "placeholder": "Es. tachipirina 500 oppure 012745093"})
            self.order_fields(["official_lookup"])
        else:
            del self.fields["official_lookup"]

    def clean_aic_code(self):
        from .official import normalize_aic

        value = "".join(self.cleaned_data.get("aic_code", "").split()).upper().removeprefix("A")
        if not value:
            return ""
        if not value.isdigit() or len(value) > 9:
            raise forms.ValidationError("Il codice AIC di una confezione è fatto di 9 cifre.")
        return normalize_aic(value)


class DrugInteractionForm(forms.ModelForm):
    class Meta:
        model = DrugInteraction
        fields = ["ingredient_a", "ingredient_b", "severity", "description", "source"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def save(self, commit=True):
        interaction = super().save(commit=False)
        if self.changed_data:  # contenuto cambiato: va rivalidato dal medico
            interaction.validated_by, interaction.validated_at = None, None
        if commit:
            interaction.save()
        return interaction


class LotLoadForm(forms.ModelForm):
    quantity = forms.DecimalField(label="Quantità caricata", min_value=0.01, decimal_places=2)

    class Meta:
        model = StockLot
        fields = ["drug", "guest", "lot_number", "expiry_date", "quantity", "supplier", "notes"]
        widgets = {"expiry_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.guests.services import guests_in_care

        self.fields["drug"].queryset = Drug.objects.filter(active=True)
        self.fields["guest"].queryset = guests_in_care()


class LotAdjustForm(forms.Form):
    kind = forms.ChoiceField(label="Tipo movimento", choices=[
        (StockMovement.Kind.ADJUSTMENT, "Rettifica inventario"),
        (StockMovement.Kind.DISPOSAL, "Smaltimento (scaduto/deteriorato)"),
        (StockMovement.Kind.RETURN, "Reso / restituzione"),
    ])
    new_quantity = forms.DecimalField(label="Nuova giacenza", min_value=0, decimal_places=2)
    notes = forms.CharField(label="Motivazione", max_length=255)
