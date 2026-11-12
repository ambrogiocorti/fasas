from django import forms
from django.forms import modelformset_factory
from django.utils import timezone

from fasas.accounts.models import User
from fasas.guests.forms import DateInput

from .models import Code, CredentialType, LeaveRequest, RotaSettings, ShiftChange, StaffProfile


class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["kind", "start", "end", "note"]
        widgets = {"start": DateInput(), "end": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [c for c in LeaveRequest.Kind.choices if c[0] != LeaveRequest.Kind.SICK]

    def clean(self):
        data = super().clean()
        if data.get("start") and data["start"] < timezone.localdate():
            self.add_error("start", "Le richieste si fanno per giorni futuri; per le assenze passate avvisare il coordinatore.")
        return data


class ShiftChangeForm(forms.Form):
    kind = forms.ChoiceField(label="Tipo", choices=ShiftChange.Kind.choices)
    date = forms.DateField(label="Giorno", widget=DateInput())
    colleague = forms.ModelChoiceField(label="Collega", queryset=User.objects.none())
    note = forms.CharField(label="Motivo", required=False, max_length=255)

    def __init__(self, *args, user=None, colleagues=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["colleague"].queryset = User.objects.filter(pk__in=[c.pk for c in colleagues]).exclude(
            pk=getattr(user, "pk", None)).order_by("last_name")


class DecisionForm(forms.Form):
    note = forms.CharField(label="Nota", required=False, max_length=255)


class RotaSettingsForm(forms.ModelForm):
    class Meta:
        model = RotaSettings
        exclude = ["community"]


StaffProfileFormSet = modelformset_factory(
    StaffProfile, fields=["in_rota", "weekly_hours", "can_lead", "no_nights", "order"], extra=0)

PAINT_CODES = [("", "Vuoto")] + list(Code.choices)


class CredentialForm(forms.Form):
    user = forms.ModelChoiceField(label="Dipendente", queryset=User.objects.none())
    type = forms.ModelChoiceField(label="Corso, idoneità o visita", queryset=CredentialType.objects.none())
    obtained_on = forms.DateField(label="Conseguito / visita del", widget=DateInput())
    expires_on = forms.DateField(label="Scadenza", required=False, widget=DateInput(),
                                 help_text="Se vuota si calcola dalla validità del tipo. Per l'idoneità: la data "
                                           "della prossima visita indicata nel giudizio.")
    provider = forms.CharField(label="Ente o medico", max_length=120, required=False)
    notes = forms.CharField(label="Note", max_length=255, required=False,
                            help_text="Non indicare diagnosi né limitazioni sanitarie dettagliate.")
    certificate = forms.FileField(label="Attestato (PDF o foto, facoltativo)", required=False,
                                  widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf",
                                                                         "capture": "environment"}))

    def __init__(self, *args, users=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(pk__in=[u.pk for u in users]).order_by("last_name")
        self.fields["type"].queryset = CredentialType.objects.filter(active=True)


class CredentialTypeForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(label="Obbligatorio per i ruoli", required=False,
                                      widget=forms.CheckboxSelectMultiple,
                                      help_text="Vuoto = solo per chi è designato (es. addetti antincendio).")

    class Meta:
        model = CredentialType
        fields = ["name", "category", "validity_months", "warn_days", "roles", "reference", "active", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.accounts.models import Role

        self.fields["roles"].choices = [(r.value, r.label) for r in Role if r != Role.ADMIN]
