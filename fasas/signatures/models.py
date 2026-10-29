from django.conf import settings
from django.db import models
from django.utils import timezone


class SigningCredential(models.Model):
    """
    Credenziale di firma di un utente (tipicamente il medico).

    - pkcs12: certificato personale (.p12/.pfx) cifrato con la chiave di sistema; la passphrase
      NON viene mai salvata e va digitata a ogni firma.
    - remote: firma remota presso un prestatore qualificato (QTSP) tramite API CSC; si salvano
      solo l'utente e l'identificativo della credenziale presso il prestatore. Password, PIN e OTP
      si digitano a ogni firma e non vengono mai salvati.
    """

    class OTPType(models.TextChoices):
        NONE = "", "Nessuno"
        OFFLINE = "offline", "OTP da app o dispositivo"
        ONLINE = "online", "OTP via SMS"

    class Kind(models.TextChoices):
        PKCS12 = "pkcs12", "Certificato PKCS#12"
        REMOTE = "remote", "Firma remota qualificata (QTSP)"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signing_credential")
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.PKCS12)
    storage_name = models.CharField(max_length=255, blank=True, editable=False)
    remote_user_id = models.CharField("utente presso il provider di firma remota", max_length=150, blank=True)
    remote_credential_id = models.CharField("identificativo credenziale (CSC)", max_length=255, blank=True)
    remote_pin_required = models.BooleanField("richiede PIN", default=False)
    remote_otp_type = models.CharField("tipo OTP", max_length=10, choices=OTPType.choices, blank=True)
    certificate_subject = models.CharField("titolare certificato", max_length=255, blank=True)
    certificate_issuer = models.CharField("emittente", max_length=255, blank=True)
    certificate_serial = models.CharField("seriale", max_length=100, blank=True)
    valid_from = models.DateTimeField("valido dal", null=True, blank=True)
    valid_to = models.DateTimeField("valido fino al", null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "credenziale di firma"
        verbose_name_plural = "credenziali di firma"
        permissions = [("sign_document", "Può firmare digitalmente i documenti sanitari")]

    def __str__(self):
        return f"{self.user} – {self.certificate_subject or self.get_kind_display()}"

    @property
    def is_valid_now(self):
        now = timezone.now()
        return (self.valid_from is None or self.valid_from <= now) and (self.valid_to is None or now <= self.valid_to)


class Signature(models.Model):
    source_version = models.ForeignKey(
        "documents.DocumentVersion", on_delete=models.PROTECT, related_name="signatures_requested"
    )
    signed_version = models.OneToOneField(
        "documents.DocumentVersion", on_delete=models.PROTECT, related_name="signature"
    )
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signatures")
    signed_at = models.DateTimeField("firmato il", default=timezone.now)
    signature_format = models.CharField("formato", max_length=30, default="PAdES-B")
    provider = models.CharField("provider", max_length=50)
    certificate_subject = models.CharField("titolare certificato", max_length=255)
    certificate_issuer = models.CharField("emittente", max_length=255, blank=True)
    certificate_serial = models.CharField("seriale", max_length=100, blank=True)
    reason = models.CharField("motivo firma", max_length=255, blank=True)
    timestamped = models.BooleanField("marca temporale", default=False)

    class Meta:
        verbose_name = "firma digitale"
        verbose_name_plural = "firme digitali"
        ordering = ["-signed_at"]

    def __str__(self):
        return f"{self.signed_version} firmato da {self.signer}"
