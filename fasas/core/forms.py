from django import forms

from .models import Community, SystemConfig


class SystemConfigForm(forms.ModelForm):
    class Meta:
        model = SystemConfig
        exclude = ["community"]
        widgets = {
            "morning_start": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "afternoon_start": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "night_start": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def clean(self):
        cleaned = super().clean()
        m, a, n = cleaned.get("morning_start"), cleaned.get("afternoon_start"), cleaned.get("night_start")
        if m and a and n and not (m < a < n):
            raise forms.ValidationError("Gli orari dei turni devono essere in ordine: mattina < pomeriggio < notte.")
        return cleaned


class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ["name", "address", "phone", "email", "asl_code"]
