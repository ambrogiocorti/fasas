from django import forms

from fasas.guests.forms import DateInput

from .models import Drug, DrugInteraction, StockLot, StockMovement


class DrugForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = "__all__"
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class DrugInteractionForm(forms.ModelForm):
    class Meta:
        model = DrugInteraction
        fields = "__all__"
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


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
