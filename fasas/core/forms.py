from django import forms

from .models import Community, SystemConfig


class SystemConfigForm(forms.ModelForm):
    class Meta:
        model = SystemConfig
        exclude = ["community", "disabled_modules"]
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
        if cleaned.get("documents_cie_required"):
            from fasas.signatures import cie, external, nis

            unchanged = (self.instance.pk and self.instance.documents_cie_required
                         and self.instance.documents_verification == cleaned.get("documents_verification"))
            if not unchanged and not cie.is_enabled():
                self.add_error("documents_cie_required", "Prima va attivata la CIE sul server (FASAS_CIE_ENABLED, "
                               "docs/FIRMA_CIE.md): altrimenti nessuno aprirebbe più i documenti.")
            elif not unchanged and cleaned.get("documents_verification") == "nis" and not nis.csca_certificates():
                self.add_error("documents_verification", "Per la CIE con il PIN FASAS servono i certificati della CSCA "
                               "italiana (FASAS_CIE_CSCA, docs/FIRMA_CIE.md).")
            elif not unchanged and cleaned.get("documents_verification") == "cie" and not external.trust_roots():
                self.add_error("documents_verification", "Per la CIE con il suo PIN servono i certificati delle CA "
                               "della CIE (FASAS_CIE_TRUST_ROOTS, docs/FIRMA_CIE.md).")
        return cleaned


class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ["name", "address", "phone", "email", "asl_code"]
