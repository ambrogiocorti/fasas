from django import forms

from .models import Feedback


class FeedbackForm(forms.ModelForm):
    text = forms.CharField(
        label="Cosa è successo", max_length=1500, widget=forms.Textarea(attrs={"rows": 5}),
        help_text="Cosa stavi facendo, cosa ti aspettavi, cosa è successo. Non scrivere nomi o dati sanitari degli "
                  "ospiti: la pagina e l'ora si salvano da sole.")

    class Meta:
        model = Feedback
        fields = ["kind", "text"]
        widgets = {"kind": forms.RadioSelect}


class FeedbackReplyForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["status", "reply"]
        widgets = {"reply": forms.Textarea(attrs={"rows": 2})}
