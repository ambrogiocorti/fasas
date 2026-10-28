from django import forms


class CredentialForm(forms.Form):
    certificate = forms.FileField(label="Certificato di firma (.p12 / .pfx)")
    passphrase = forms.CharField(
        label="Passphrase del certificato", widget=forms.PasswordInput,
        help_text="Serve solo a verificare il certificato: non viene salvata.",
    )


class RemoteCredentialForm(forms.Form):
    remote_user_id = forms.CharField(label="Utente presso il servizio di firma remota")
    certificate_subject = forms.CharField(label="Titolare del certificato (come da contratto)")


class SignForm(forms.Form):
    secret = forms.CharField(
        label="Passphrase / OTP", widget=forms.PasswordInput(attrs={"autocomplete": "one-time-code"}),
        help_text="Passphrase del certificato o codice OTP della firma remota.",
    )
    reason = forms.CharField(label="Motivo della firma", initial="Documento sanitario FASAS", max_length=255)
    confirm = forms.BooleanField(label="Ho letto il documento e intendo firmarlo")
