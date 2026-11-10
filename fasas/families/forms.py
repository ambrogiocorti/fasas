from django import forms

from fasas.accounts.models import User
from fasas.documents.models import Document
from fasas.guests.forms import DateInput

from .models import FamilyLink


class MessageForm(forms.Form):
    body = forms.CharField(label="Messaggio", max_length=2000,
                           widget=forms.Textarea(attrs={"rows": 3, "maxlength": 2000}))


class VisitForm(forms.Form):
    day = forms.DateField(label="Giorno", widget=DateInput())
    time = forms.TimeField(label="Ora", widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"))
    people = forms.IntegerField(label="Persone", min_value=1, max_value=6, initial=1)
    notes = forms.CharField(label="Note", max_length=255, required=False,
                            help_text="Es. «porto il cane», «vorrei uscire in giardino».")


class DecisionForm(forms.Form):
    note = forms.CharField(label="Nota per il familiare", max_length=255, required=False)


class LinkForm(forms.ModelForm):
    class Meta:
        model = FamilyLink
        fields = ["user", "guest", "relation", "description", "basis", "can_see_documents", "can_see_cash", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.accounts.models import Role
        from fasas.guests.models import Guest

        self.fields["user"].queryset = User.objects.filter(role=Role.FAMILY, is_active=True).order_by("last_name")
        self.fields["user"].help_text = ("L'utente lo crea l'amministratore in «Utenti e permessi» con il ruolo "
                                         "«Familiare o tutore».")
        self.fields["guest"].queryset = Guest.objects.exclude(status=Guest.Status.ARCHIVED).order_by("last_name")


class RevokeForm(forms.Form):
    reason = forms.CharField(label="Motivo della revoca", max_length=255)


class ShareForm(forms.Form):
    document = forms.ModelChoiceField(label="Documento", queryset=Document.objects.none())
    note = forms.CharField(label="Nota per i familiari", max_length=255, required=False)

    def __init__(self, *args, guest=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import SharedDocument

        shared = SharedDocument.objects.filter(document__guest=guest, revoked_at__isnull=True).values("document_id")
        self.fields["document"].queryset = guest.documents.exclude(pk__in=shared).order_by("-updated_at")
