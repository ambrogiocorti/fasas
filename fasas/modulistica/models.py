"""
Modulistica: moduli configurabili dal gestore del sistema (informative, autorizzazioni, consensi, accordi, richieste),
compilabili online o stampabili su carta. Ogni compilazione conserva una fotografia del testo e delle risposte, così
un modulo modificato in seguito non cambia ciò che è stato compilato.
"""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from fasas.core.models import Community, TimeStampedModel


class FormSettings(models.Model):
    """Intestazione dei moduli: titolare del trattamento e responsabile della protezione dei dati."""

    community = models.OneToOneField(Community, on_delete=models.CASCADE, related_name="form_settings")
    holder = models.CharField("titolare del trattamento", max_length=200, blank=True,
                              help_text="Ragione sociale dell'ente gestore.")
    address = models.CharField("sede", max_length=255, blank=True)
    contacts = models.CharField("recapiti del titolare", max_length=255, blank=True, help_text="Email o PEC, telefono.")
    dpo = models.CharField("responsabile della protezione dei dati (DPO)", max_length=200, blank=True)
    dpo_contacts = models.CharField("recapiti del DPO", max_length=255, blank=True)

    class Meta:
        verbose_name = "intestazione dei moduli"
        verbose_name_plural = "intestazione dei moduli"

    def __str__(self):
        return self.holder or "Intestazione dei moduli"

    @classmethod
    def get(cls):
        community = Community.default()
        obj, created = cls.objects.get_or_create(community=community)
        if created:
            obj.holder, obj.address, obj.contacts = community.name, community.address, community.email
            obj.save()
        return obj

    @property
    def complete(self):
        return all([self.holder, self.address, self.contacts, self.dpo, self.dpo_contacts])

    def variables(self):
        return {"titolare": self.holder, "sede": self.address, "contatti": self.contacts, "dpo": self.dpo,
                "contatti_dpo": self.dpo_contacts, "struttura": self.community.name}


class FormTemplate(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Bozza"
        PUBLISHED = "published", "Pubblicato"
        ARCHIVED = "archived", "Archiviato"

    code = models.SlugField("codice", max_length=60, unique=True)
    title = models.CharField("titolo", max_length=200)
    intro = models.TextField("testo", blank=True,
                             help_text="Paragrafi separati da una riga vuota; «- » per gli elenchi; **grassetto**. "
                                       "Variabili: {titolare} {sede} {contatti} {dpo} {contatti_dpo} {struttura} "
                                       "{ospite} {utente} {ruolo}.")
    for_guests = models.BooleanField("ospiti e rappresentanti (compilato in struttura)", default=False)
    for_family = models.BooleanField("familiari (online, dall'area familiari)", default=False)
    for_staff = models.BooleanField("personale", default=False)
    staff_roles = models.JSONField("ruoli del personale", default=list, blank=True)
    auto_assign = models.BooleanField("chiedere anche ai nuovi utenti", default=False,
                                      help_text="Ogni nuovo utente dei ruoli indicati lo trova tra «I miei moduli».")
    requires_signature = models.BooleanField(
        "richiede la firma", default=False,
        help_text="Dopo la compilazione online si stampa, si firma a mano e si carica la scansione (o si firma "
                  "digitalmente). La conferma online da sola registra chi ha risposto, ma non è una firma.")
    withdrawable = models.BooleanField("revocabile (consenso)", default=False)
    signatures = models.JSONField("righe per le firme", default=list, blank=True)
    document_category = models.CharField("categoria nel fascicolo dell'ospite", max_length=30, default="form")
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveSmallIntegerField("versione", default=1)
    published_at = models.DateTimeField("pubblicato il", null=True, blank=True)
    order = models.PositiveSmallIntegerField("ordine", default=0)

    class Meta:
        verbose_name = "modulo"
        verbose_name_plural = "moduli"
        ordering = ["order", "title"]
        permissions = [("manage_forms", "Gestisce la modulistica (testi, pubblicazione, distribuzione)")]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    @property
    def audiences(self):
        return [label for flag, label in ((self.for_guests, "ospiti"), (self.for_family, "familiari"),
                                          (self.for_staff, "personale")) if flag]

    def get_absolute_url(self):
        return reverse("modulistica:edit", args=[self.pk])


class FormField(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "Testo breve"
        TEXTAREA = "textarea", "Testo lungo"
        DATE = "date", "Data"
        CHOICE = "choice", "Una scelta"
        MULTI = "multi", "Più scelte"
        CHECK = "check", "Dichiarazione da spuntare"
        SECTION = "section", "Sottotitolo"

    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name="fields")
    key = models.SlugField("chiave", max_length=40)
    label = models.CharField("domanda o dichiarazione", max_length=255)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.TEXT)
    required = models.BooleanField("obbligatorio", default=False)
    options = models.JSONField("opzioni", default=list, blank=True)
    help_text = models.CharField("suggerimento", max_length=255, blank=True)
    order = models.PositiveSmallIntegerField("ordine", default=0)

    class Meta:
        verbose_name = "campo del modulo"
        verbose_name_plural = "campi del modulo"
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["template", "key"], name="unique_form_field_key")]

    def __str__(self):
        return self.label


class FormAssignment(models.Model):
    """Modulo da compilare da un utente del personale (distribuito dal gestore del sistema)."""

    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="form_assignments")
    version = models.PositiveSmallIntegerField(default=1)
    assigned_at = models.DateTimeField(default=timezone.now)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+")
    due_date = models.DateField("entro il", null=True, blank=True)
    submission = models.OneToOneField("FormSubmission", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="assignment")
    cancelled = models.BooleanField(default=False)

    class Meta:
        verbose_name = "modulo da compilare"
        verbose_name_plural = "moduli da compilare"
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.template} – {self.user}"

    @property
    def pending(self):
        return self.submission_id is None and not self.cancelled


class FormSubmission(models.Model):
    class Channel(models.TextChoices):
        ONLINE = "online", "Compilato online"
        PAPER = "paper", "Cartaceo (scansione)"

    template = models.ForeignKey(FormTemplate, on_delete=models.PROTECT, related_name="submissions")
    version = models.PositiveSmallIntegerField()
    snapshot = models.JSONField(default=dict)  # titolo, testo, campi e firme com'erano al momento della compilazione
    answers = models.JSONField(default=dict)
    guest = models.ForeignKey("guests.Guest", on_delete=models.PROTECT, null=True, blank=True,
                              related_name="form_submissions")
    family_link = models.ForeignKey("families.FamilyLink", on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="form_submissions")
    subject_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="form_submissions", help_text="Utente del personale interessato.")
    respondent = models.CharField("compilato da (nome)", max_length=200, blank=True)
    respondent_role = models.CharField("in qualità di", max_length=100, blank=True)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.ONLINE)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    pdf_storage = models.CharField(max_length=255, blank=True, editable=False)
    pdf_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    signed_storage = models.CharField(max_length=255, blank=True, editable=False)
    signed_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    signed_type = models.CharField(max_length=60, blank=True, editable=False)
    signed_at = models.DateTimeField("firmato (scansione caricata) il", null=True, blank=True)
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+")
    document = models.ForeignKey("documents.Document", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", help_text="Copia nel fascicolo dell'ospite.")
    withdrawn_at = models.DateTimeField("revocato il", null=True, blank=True)
    withdrawn_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+")
    withdraw_reason = models.CharField("motivo della revoca", max_length=255, blank=True)

    class Meta:
        verbose_name = "modulo compilato"
        verbose_name_plural = "moduli compilati"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.snapshot.get('title', self.template)} – {self.created_at:%d/%m/%Y}"

    @property
    def needs_signature(self):
        return bool(self.snapshot.get("requires_signature")) and not self.signed_at and not self.withdrawn_at

    @property
    def status(self):
        if self.withdrawn_at:
            return "revocato"
        if self.snapshot.get("requires_signature"):
            return "firmato" if self.signed_at else "da firmare"
        return "confermato online" if self.channel == self.Channel.ONLINE else "acquisito"
