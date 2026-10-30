from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm

from fasas.core.middleware import client_ip

from .models import AccessLog, User
from .services import is_locked_out, record_access


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": "Troppi tentativi falliti. Riprova tra qualche minuto o contatta l'amministratore.",
    }

    def clean(self):
        username = self.cleaned_data.get("username", "")
        if username and is_locked_out(username, client_ip(self.request)):
            record_access(self.request, AccessLog.Event.LOCKED, username)
            raise forms.ValidationError(self.error_messages["locked"], code="locked")
        return super().clean()


class OTPForm(forms.Form):
    code = forms.CharField(
        label="Codice di verifica", max_length=20,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True,
                                      "placeholder": "6 cifre dall'app"}),
        help_text="Il codice di 6 cifre dell'app sul telefono. Senza telefono: un codice di recupero (es. abcde-fghjk).",
    )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "theme"]


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "username", "first_name", "last_name", "email", "fiscal_code", "phone",
            "role", "qualification", "professional_register", "is_active",
        ]

    def clean_fiscal_code(self):
        return self.cleaned_data["fiscal_code"].upper().strip()


class UserCreateForm(UserForm):
    password1 = forms.CharField(label="Password iniziale", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Conferma password", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Le password non coincidono.")
        elif cleaned.get("password1"):
            from django.contrib.auth.password_validation import validate_password

            try:
                validate_password(cleaned["password1"], self.instance)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AdminSetPasswordForm(SetPasswordForm):
    pass
