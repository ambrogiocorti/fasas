import datetime
import uuid

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


class LegalLevel(models.TextChoices):
    """Valore giuridico dichiarato della firma: mai «qualificata» senza tutti i requisiti verificati."""

    FEQ = "feq", "Firma elettronica qualificata"
    FEA = "fea", "Firma elettronica avanzata"
    FE = "fe", "Firma elettronica (non qualificata)"



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
    legal_level = models.CharField("valore giuridico", max_length=3, choices=LegalLevel.choices, blank=True)

    class Meta:
        verbose_name = "firma digitale"
        verbose_name_plural = "firme digitali"
        ordering = ["-signed_at"]

    def __str__(self):
        return f"{self.signed_version} firmato da {self.signer}"


class SignerDevice(models.Model):
    """
    Computer o telefono abbinato a un utente per firmare con la CIE (FASAS Signer).
    Il dispositivo si autentica con un token casuale di cui il server conserva solo l'impronta SHA-256;
    non riceve mai il PIN, che resta sul dispositivo e va solo alla carta.
    """

    class Platform(models.TextChoices):
        WINDOWS = "windows", "Windows"
        MACOS = "macos", "macOS"
        LINUX = "linux", "Linux"
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        OTHER = "other", "Altro"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signer_devices")
    name = models.CharField("nome", max_length=100)
    platform = models.CharField("piattaforma", max_length=10, choices=Platform.choices, default=Platform.OTHER)
    app_version = models.CharField("versione app", max_length=30, blank=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField("abbinato il", default=timezone.now)
    last_seen_at = models.DateTimeField("ultimo contatto", null=True, blank=True)
    revoked_at = models.DateTimeField("revocato il", null=True, blank=True)
    status = models.JSONField("stato componenti", default=dict, blank=True)
    status_at = models.DateTimeField("stato aggiornato il", null=True, blank=True)

    class Meta:
        verbose_name = "dispositivo di firma"
        verbose_name_plural = "dispositivi di firma"
        ordering = ["-created_at"]
        permissions = [("manage_signer_devices", "Può revocare i dispositivi di firma di tutti gli utenti")]

    def __str__(self):
        return f"{self.name} ({self.get_platform_display()}) – {self.user}"

    @property
    def is_active(self):
        return self.revoked_at is None

    @property
    def is_online(self):
        return self.last_seen_at is not None and timezone.now() - self.last_seen_at < datetime.timedelta(seconds=90)


class DevicePairing(models.Model):
    """Codice monouso (pochi minuti) mostrato nel FASAS e digitato nel FASAS Signer per abbinarlo all'utente."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    code_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    device = models.OneToOneField(SignerDevice, on_delete=models.PROTECT, null=True, blank=True, related_name="pairing")

    class Meta:
        verbose_name = "codice di abbinamento"
        verbose_name_plural = "codici di abbinamento"


class SignatureRequest(models.Model):
    """
    Richiesta di firma con la CIE. Ciclo di vita del documento:
    BOZZA → IN ATTESA DI FIRMA (waiting, card, authorizing) → FIRMA IN CORSO (signing, verifying) → FIRMATO,
    oppure ERRORE (failed), ANNULLATO (cancelled) o SCADUTO (expired). Durante la firma la versione è bloccata.
    Ogni passaggio richiede il nonce corrente, che cambia a ogni passo: una risposta registrata non si riusa.
    """

    class Status(models.TextChoices):
        WAITING = "waiting", "In attesa della CIE"
        CARD = "card", "Carta rilevata"
        AUTHORIZING = "authorizing", "Autorizzazione richiesta"
        SIGNING = "signing", "Firma in corso"
        VERIFYING = "verifying", "Verifica della firma"
        SIGNED = "signed", "Documento firmato correttamente"
        FAILED = "failed", "Firma non riuscita"
        CANCELLED = "cancelled", "Annullata"
        EXPIRED = "expired", "Scaduta"

    class Purpose(models.TextChoices):
        DOCUMENT = "document", "Documento"
        TEST = "test", "Prova di funzionamento"
        ACCEPTANCE = "acceptance", "Accettazione delle condizioni della FEA"

    ACTIVE = ("waiting", "card", "authorizing", "signing", "verifying")
    CANCELLABLE = ("waiting", "card", "authorizing", "signing")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField("scopo", max_length=10, choices=Purpose.choices, default=Purpose.DOCUMENT)
    version = models.ForeignKey("documents.DocumentVersion", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="signature_requests")
    version_sha256 = models.CharField("impronta della versione bloccata", max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signature_requests")
    device = models.ForeignKey(SignerDevice, on_delete=models.PROTECT, null=True, blank=True, related_name="requests")
    status = models.CharField("stato", max_length=12, choices=Status.choices, default=Status.WAITING, db_index=True)
    reason = models.CharField("motivo", max_length=255, blank=True)
    location = models.CharField("luogo", max_length=255, blank=True)
    verify_code = models.CharField("codice di controllo", max_length=9)
    nonce_hash = models.CharField(max_length=64, editable=False)
    attempt = models.PositiveSmallIntegerField("tentativo", default=1)
    previous = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, related_name="retry")
    created_at = models.DateTimeField("creata il", default=timezone.now)
    updated_at = models.DateTimeField("aggiornata il", default=timezone.now)
    expires_at = models.DateTimeField("scade il")
    completed_at = models.DateTimeField("conclusa il", null=True, blank=True)
    certificate = models.TextField("certificato (DER base64)", blank=True)
    certificate_subject = models.CharField("titolare certificato", max_length=255, blank=True)
    certificate_issuer = models.CharField("emittente", max_length=255, blank=True)
    certificate_serial = models.CharField("seriale", max_length=100, blank=True)
    certificate_fingerprint = models.CharField("impronta certificato", max_length=64, blank=True)
    with_timestamp = models.BooleanField("con marca temporale", default=False)
    prepared = models.JSONField(default=dict, blank=True, editable=False)
    prepared_storage = models.CharField(max_length=255, blank=True, editable=False)
    result_storage = models.CharField(max_length=255, blank=True, editable=False)  # solo per le prove
    verification = models.JSONField("esito verifica", default=dict, blank=True)
    signature = models.OneToOneField(Signature, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="cie_request")
    error_code = models.CharField("codice errore", max_length=40, blank=True)
    error_message = models.CharField("errore", max_length=255, blank=True)
    pin_attempts_left = models.PositiveSmallIntegerField("tentativi PIN rimasti", null=True, blank=True)

    class Meta:
        verbose_name = "richiesta di firma con CIE"
        verbose_name_plural = "richieste di firma con CIE"
        ordering = ["-created_at"]
        permissions = [("sign_with_cie", "Può firmare i documenti con la CIE (firma elettronica avanzata)")]
        constraints = [
            # Una sola firma alla volta per versione: niente richieste duplicate né documenti divergenti
            models.UniqueConstraint(fields=["version"], condition=models.Q(status__in=(
                "waiting", "card", "authorizing", "signing", "verifying")), name="one_active_cie_request_per_version"),
        ]

    def __str__(self):
        return f"Firma CIE {self.verify_code} – {self.get_status_display()}"

    @property
    def is_active(self):
        return self.status in self.ACTIVE

    @property
    def is_test_card(self):
        """Firmata con una carta di prova (manage.py fasas_carta_di_prova, vedi external.TEST_MARKER), non con una CIE."""
        return "SOLO PROVA" in (self.certificate_issuer or "").upper()

    @property
    def document_state(self):
        if self.status in ("waiting", "card", "authorizing"):
            return "IN_ATTESA_DI_FIRMA"
        if self.status in ("signing", "verifying"):
            return "FIRMA_IN_CORSO"
        return {"signed": "FIRMATO", "failed": "ERRORE", "cancelled": "ANNULLATO", "expired": "ANNULLATO"}[self.status]


class FEAAcceptance(models.Model):
    """
    Dichiarazione di accettazione delle condizioni della firma elettronica avanzata con CIE (DPCM 22/02/2013,
    art. 57): firmata dal firmatario con la propria CIE prima della prima firma e conservata almeno 20 anni,
    insieme al certificato che lo identifica. Il firmatario ne può scaricare copia in ogni momento.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="firmatario", on_delete=models.PROTECT,
                             related_name="fea_acceptances")
    request = models.OneToOneField(SignatureRequest, on_delete=models.PROTECT, related_name="fea_acceptance")
    accepted_at = models.DateTimeField("accettata il", default=timezone.now)
    terms_version = models.CharField("versione delle condizioni", max_length=40)
    terms_sha256 = models.CharField("impronta del testo delle condizioni", max_length=64)
    signed_storage = models.CharField(max_length=255, editable=False)
    signed_sha256 = models.CharField("impronta del PDF firmato", max_length=64)
    certificate = models.TextField("certificato della CIE (DER base64)")
    certificate_subject = models.CharField("titolare certificato", max_length=255)
    certificate_serial = models.CharField("seriale", max_length=100)
    is_test_card = models.BooleanField("carta di prova (nessun valore legale)", default=False)
    retain_until = models.DateField("conservare fino al")
    revoked_at = models.DateTimeField("revocata il", null=True, blank=True)
    revoked_reason = models.CharField("motivo della revoca", max_length=255, blank=True)

    class Meta:
        verbose_name = "accettazione condizioni FEA"
        verbose_name_plural = "accettazioni condizioni FEA"
        ordering = ["-accepted_at"]
        default_permissions = ("view",)

    def __str__(self):
        return f"Accettazione FEA di {self.user} del {timezone.localtime(self.accepted_at):%d/%m/%Y}"

    @property
    def is_valid(self):
        return self.revoked_at is None

    def delete(self, *args, **kwargs):
        raise PermissionError("Le accettazioni della FEA vanno conservate almeno 20 anni: si revocano, non si cancellano.")
