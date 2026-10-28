from django import forms

from fasas.accounts.models import User
from fasas.guests.forms import DateTimeInput

from .models import Appointment


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["guest", "kind", "title", "scheduled_at", "location", "doctor", "companion", "companion_name",
                  "transport", "preparation"]
        widgets = {"scheduled_at": DateTimeInput(), "preparation": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from fasas.guests.services import guests_in_care

        self.fields["guest"].queryset = guests_in_care()
        self.fields["companion"].queryset = User.objects.filter(is_active=True)


class OutcomeForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["status", "outcome", "follow_up", "document"]
        widgets = {"outcome": forms.Textarea(attrs={"rows": 4}), "follow_up": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document"].queryset = self.instance.guest.documents.all()
        self.fields["document"].help_text = "Caricare prima il referto nei documenti dell'ospite."
