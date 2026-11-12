"""
Lesioni cutanee (in particolare da pressione) e medicazioni.

Il FASAS registra ciò che l'équipe osserva e fa: sede, categoria, misure, fondo, essudato, foto, piano di
medicazione indicato da infermiere o medico e medicazioni eseguite. Non assegna da solo la categoria della lesione
né propone il trattamento.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse

from fasas.core.models import ShiftRecordModel, TimeStampedModel


class Stage(models.TextChoices):
    """Classificazione internazionale NPIAP/EPUAP/PPPIA delle lesioni da pressione."""

    CAT1 = "1", "Categoria 1 – eritema non sbiancabile"
    CAT2 = "2", "Categoria 2 – perdita parziale dello spessore cutaneo"
    CAT3 = "3", "Categoria 3 – perdita totale dello spessore cutaneo"
    CAT4 = "4", "Categoria 4 – perdita totale dello spessore tissutale"
    UNSTAGEABLE = "U", "Non stadiabile (fondo non visibile)"
    DEEP = "DTI", "Sospetta lesione dei tessuti profondi"


class Wound(ShiftRecordModel):
    """Una lesione, dalla prima osservazione (data e ora della registrazione) alla guarigione."""

    class Kind(models.TextChoices):
        PRESSURE = "pressure", "Lesione da pressione"
        MOISTURE = "moisture", "Dermatite da umidità o incontinenza"
        SKIN_TEAR = "skin_tear", "Lacerazione cutanea (skin tear)"
        SURGICAL = "surgical", "Ferita chirurgica"
        TRAUMATIC = "traumatic", "Ferita traumatica"
        VASCULAR = "vascular", "Ulcera vascolare o del piede diabetico"
        OTHER = "other", "Altro"

    class Site(models.TextChoices):
        SACRUM = "sacrum", "Sacro / coccige"
        HEEL = "heel", "Tallone"
        ISCHIUM = "ischium", "Ischio (gluteo)"
        TROCHANTER = "trochanter", "Trocantere (anca)"
        MALLEOLUS = "malleolus", "Malleolo"
        ELBOW = "elbow", "Gomito"
        SCAPULA = "scapula", "Scapola"
        OCCIPUT = "occiput", "Nuca / occipite"
        EAR = "ear", "Orecchio"
        SPINE = "spine", "Colonna vertebrale"
        LEG = "leg", "Gamba"
        FOOT = "foot", "Piede / dita"
        ARM = "arm", "Braccio / mano"
        OTHER = "other", "Altra sede"

    class Side(models.TextChoices):
        NONE = "", "—"
        LEFT = "left", "sinistra"
        RIGHT = "right", "destra"

    class Origin(models.TextChoices):
        IN_HOUSE = "in_house", "Insorta in struttura"
        ADMISSION = "admission", "Già presente all'ingresso"
        AWAY = "away", "Insorta durante ricovero o assenza"

    class Status(models.TextChoices):
        OPEN = "open", "Aperta"
        HEALED = "healed", "Guarita"
        CLOSED = "closed", "Chiusa per altro motivo"

    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.PRESSURE)
    site = models.CharField("sede", max_length=20, choices=Site.choices)
    side = models.CharField("lato", max_length=5, choices=Side.choices, blank=True)
    site_detail = models.CharField("sede, dettaglio", max_length=120, blank=True)
    origin = models.CharField("insorgenza", max_length=20, choices=Origin.choices, default=Origin.IN_HOUSE)
    stage = models.CharField("categoria alla prima osservazione", max_length=3, choices=Stage.choices, blank=True,
                             help_text="Solo per le lesioni da pressione.")
    description = models.TextField("descrizione", blank=True)
    check_interval_days = models.PositiveSmallIntegerField(
        "rivalutare ogni (giorni)", default=7, help_text="Misure, fondo ed eventuale foto: di solito ogni settimana.")
    status = models.CharField("stato", max_length=10, choices=Status.choices, default=Status.OPEN, editable=False)
    closed_at = models.DateTimeField("chiusa il", null=True, blank=True, editable=False)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="chiusa da", on_delete=models.PROTECT,
                                  null=True, blank=True, related_name="+", editable=False)
    close_note = models.TextField("nota di chiusura", blank=True, editable=False)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "lesione"
        verbose_name_plural = "lesioni"

    def __str__(self):
        return f"{self.get_kind_display()} – {self.site_display}"

    def get_absolute_url(self):
        return reverse("wounds:detail", args=[self.pk])

    @property
    def site_display(self):
        parts = [self.get_site_display()]
        if self.side:
            parts.append(self.get_side_display())
        text = " ".join(parts)
        return f"{text} ({self.site_detail})" if self.site_detail else text

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def last_check(self):
        return self.checks.order_by("-occurred_at").first()

    @property
    def current_stage(self):
        """Categoria dell'ultima rilevazione che la indica, altrimenti quella della prima osservazione."""
        check = self.checks.exclude(stage="").order_by("-occurred_at").first()
        return check.get_stage_display() if check else self.get_stage_display()

    @property
    def active_plan(self):
        return self.plans.filter(active=True).order_by("-start_date", "-pk").first()


class WoundCheck(ShiftRecordModel):
    """Rilevazione periodica della lesione: misure, fondo, essudato, cute circostante, dolore, foto."""

    class Bed(models.TextChoices):
        EPITHELIAL = "epithelial", "Riepitelizzazione (rosa)"
        GRANULATION = "granulation", "Granulazione (rosso)"
        SLOUGH = "slough", "Fibrina / slough (giallo)"
        NECROSIS = "necrosis", "Necrosi / escara (nero)"
        MIXED = "mixed", "Misto"
        INTACT = "intact", "Cute integra (eritema)"

    class Exudate(models.TextChoices):
        NONE = "none", "Assente"
        LOW = "low", "Scarso"
        MODERATE = "moderate", "Moderato"
        HIGH = "high", "Abbondante"

    class Periwound(models.TextChoices):
        INTACT = "intact", "Integra"
        ERYTHEMA = "erythema", "Arrossata"
        MACERATED = "macerated", "Macerata"
        DRY = "dry", "Secca / desquamata"
        OEDEMA = "oedema", "Edematosa"

    wound = models.ForeignKey(Wound, verbose_name="lesione", on_delete=models.PROTECT, related_name="checks")
    stage = models.CharField("categoria", max_length=3, choices=Stage.choices, blank=True)
    length_cm = models.DecimalField("lunghezza (cm)", max_digits=4, decimal_places=1, null=True, blank=True)
    width_cm = models.DecimalField("larghezza (cm)", max_digits=4, decimal_places=1, null=True, blank=True)
    depth_cm = models.DecimalField("profondità (cm)", max_digits=4, decimal_places=1, null=True, blank=True)
    bed = models.CharField("fondo", max_length=12, choices=Bed.choices, blank=True)
    exudate = models.CharField("essudato", max_length=10, choices=Exudate.choices, blank=True)
    periwound = models.CharField("cute circostante", max_length=10, choices=Periwound.choices, blank=True)
    odour = models.BooleanField("cattivo odore", default=False)
    infection_signs = models.BooleanField("segni di infezione (calore, gonfiore, pus, febbre)", default=False)
    pain = models.PositiveSmallIntegerField("dolore (0–10)", null=True, blank=True)
    notes = models.TextField("note", blank=True)
    photo = models.ForeignKey("documents.Document", verbose_name="foto", on_delete=models.PROTECT, null=True,
                              blank=True, related_name="+", editable=False)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "rilevazione della lesione"
        verbose_name_plural = "rilevazioni delle lesioni"

    def __str__(self):
        return f"Rilevazione {self.wound} – {self.occurred_at:%d/%m/%Y}"

    @property
    def size_display(self):
        values = [v for v in (self.length_cm, self.width_cm, self.depth_cm) if v is not None]
        text = " × ".join(f"{Decimal(str(v)).normalize():f}".replace(".", ",") for v in values)
        return f"{text} cm" if values else ""


class DressingPlan(TimeStampedModel):
    """Medicazione indicata da infermiere o medico; una nuova indicazione chiude la precedente."""

    wound = models.ForeignKey(Wound, verbose_name="lesione", on_delete=models.PROTECT, related_name="plans")
    products = models.TextField("medicazione e prodotti", help_text="Es. detersione con soluzione fisiologica, "
                                                                      "idrocolloide extrasottile.")
    procedure = models.TextField("modalità e precauzioni", blank=True,
                                 help_text="Es. protezione della cute circostante, riposizionamento ogni 2 ore.")
    interval_days = models.PositiveSmallIntegerField("cambiare ogni (giorni)", default=2)
    start_date = models.DateField("dal")
    indicated_by = models.CharField("indicata da", max_length=120, help_text="Infermiere o medico, con la qualifica.")
    active = models.BooleanField("in corso", default=True, editable=False)
    ended_on = models.DateField("terminata il", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "piano di medicazione"
        verbose_name_plural = "piani di medicazione"
        ordering = ["-start_date", "-pk"]

    def __str__(self):
        return f"Medicazione ogni {self.interval_days} gg – {self.wound}"

    @property
    def guest(self):
        return self.wound.guest


class Dressing(ShiftRecordModel):
    """Medicazione eseguita."""

    wound = models.ForeignKey(Wound, verbose_name="lesione", on_delete=models.PROTECT, related_name="dressings")
    plan = models.ForeignKey(DressingPlan, verbose_name="piano", on_delete=models.PROTECT, null=True, blank=True,
                             related_name="dressings", editable=False)
    products_used = models.CharField("prodotti usati", max_length=255, blank=True,
                                     help_text="Vuoto = quelli del piano in corso.")
    notes = models.TextField("note", blank=True)

    class Meta(ShiftRecordModel.Meta):
        verbose_name = "medicazione"
        verbose_name_plural = "medicazioni"

    def __str__(self):
        return f"Medicazione {self.wound} – {self.occurred_at:%d/%m/%Y %H:%M}"

    @property
    def products_display(self):
        return self.products_used or (self.plan.products if self.plan else "")
