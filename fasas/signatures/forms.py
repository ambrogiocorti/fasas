from django import forms
from django.conf import settings


class CredentialForm(forms.Form):
    certificate = forms.FileField(label="Certificato di firma (.p12 / .pfx)")
    passphrase = forms.CharField(
        label="Passphrase del certificato", widget=forms.PasswordInput,
        help_text="Serve solo a verificare il certificato: non viene salvata.",
    )


class RemoteCredentialForm(forms.Form):
    remote_user_id = forms.CharField(label="Utente presso il servizio di firma remota", max_length=150)
    password = forms.CharField(
        label="Password del servizio di firma", widget=forms.PasswordInput, required=False,
        help_text="Serve solo per collegarsi al prestatore e leggere il certificato: non viene salvata.",
    )
    credential_id = forms.CharField(
        label="Identificativo della credenziale", required=False, max_length=255,
        help_text="Solo se avete più firme remote presso lo stesso prestatore",
    )

    def clean(self):
        data = super().clean()
        if settings.FASAS_CSC_AUTH == "basic" and not data.get("password"):
            self.add_error("password", "Indicare la password del servizio di firma.")
        return data


class SignForm(forms.Form):
    """I campi dipendono dallo strumento di firma del medico: nulla di quanto digitato viene salvato."""

    def __init__(self, *args, credential=None, has_token=False, **kwargs):
        super().__init__(*args, **kwargs)
        remote = credential is not None and credential.kind == "remote"
        if not remote:
            self.fields["passphrase"] = forms.CharField(label="Passphrase del certificato", widget=forms.PasswordInput)
        else:
            if settings.FASAS_CSC_AUTH == "basic" and not has_token:
                self.fields["password"] = forms.CharField(
                    label="Password del servizio di firma", widget=forms.PasswordInput(attrs={"autocomplete": "off"}))
            if credential.remote_pin_required:
                self.fields["pin"] = forms.CharField(
                    label="PIN di firma", widget=forms.PasswordInput(attrs={"autocomplete": "off", "inputmode": "numeric"}))
            if credential.remote_otp_type:
                help_text = ("Codice ricevuto via SMS: premere prima «Invia OTP»" if credential.remote_otp_type == "online"
                             else "Codice generato dall'app o dal dispositivo OTP")
                self.fields["otp"] = forms.CharField(
                    label="OTP", help_text=help_text,
                    widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}))
        self.fields["reason"] = forms.CharField(label="Motivo della firma", initial="Documento sanitario FASAS",
                                                max_length=255)
        self.fields["confirm"] = forms.BooleanField(label="Ho letto il documento e intendo firmarlo")

    def secrets(self):
        return {k: self.cleaned_data.get(k, "") for k in ("passphrase", "password", "pin", "otp")}


class SendOTPForm(forms.Form):
    password = forms.CharField(label="Password del servizio di firma", widget=forms.PasswordInput, required=False)
