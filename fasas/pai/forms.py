from django import forms

from fasas.accounts.models import User
from fasas.guests.forms import DateInput

from .models import PAI, PAIGoal


class PAIForm(forms.ModelForm):
    class Meta:
        model = PAI
        fields = ["review_due", "summary", "participants"]
        widgets = {
            "review_due": DateInput(),
            "summary": forms.Textarea(attrs={"rows": 4}),
            "participants": forms.Textarea(attrs={"rows": 2}),
        }


class PAIGoalForm(forms.ModelForm):
    class Meta:
        model = PAIGoal
        fields = ["area", "objective", "intervention", "responsible", "responsible_name", "verification_date",
                  "indicators", "order"]
        widgets = {
            "objective": forms.Textarea(attrs={"rows": 2}),
            "intervention": forms.Textarea(attrs={"rows": 3}),
            "verification_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = User.objects.filter(is_active=True)


class GoalVerificationForm(forms.ModelForm):
    class Meta:
        model = PAIGoal
        fields = ["outcome", "verification_notes", "verification_date"]
        labels = {"verification_date": "Prossima verifica"}
        widgets = {"verification_notes": forms.Textarea(attrs={"rows": 3}), "verification_date": DateInput()}
