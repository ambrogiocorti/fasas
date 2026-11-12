from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Drug(models.Model):
    class Form(models.TextChoices):
        TABLET = "tablet", "Compresse"
        CAPSULE = "capsule", "Capsule"
        DROPS = "drops", "Gocce"
        SYRUP = "syrup", "Sciroppo / soluzione orale"
        SACHET = "sachet", "Bustine"
        VIAL = "vial", "Fiale"
        SUPPOSITORY = "suppository", "Supposte"
        ENEMA = "enema", "Clistere / microclisma"
        CREAM = "cream", "Crema / pomata"
        PATCH = "patch", "Cerotto"
        INHALER = "inhaler", "Inalatore"
        OTHER = "other", "Altro"

    name = models.CharField("nome commerciale", max_length=150)
    active_ingredient = models.CharField(
        "principio attivo", max_length=150, help_text="Usato per il controllo duplicati, interazioni e allergie"
    )
    atc_code = models.CharField("codice ATC", max_length=10, blank=True, help_text="Es. N03AX09")
    aic_code = models.CharField("codice AIC", max_length=20, blank=True)
    form = models.CharField("forma farmaceutica", max_length=20, choices=Form.choices, default=Form.TABLET)
    strength = models.CharField("dosaggio confezione", max_length=60, blank=True, help_text="Es. 500 mg")
    stock_unit = models.CharField("unità di magazzino", max_length=30, default="unità", help_text="compresse, ml, fiale...")
    min_stock = models.DecimalField("soglia minima", max_digits=10, decimal_places=2, default=Decimal("0"))
    is_controlled = models.BooleanField("stupefacente / psicotropo (registro dedicato)", default=False)
    active = models.BooleanField("attivo", default=True)
    notes = models.TextField("note", blank=True)

    class Meta:
        verbose_name = "farmaco"
        verbose_name_plural = "farmaci"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} {self.strength}".strip()

    def stock_quantity(self):
        return self.lots.filter(quantity__gt=0).aggregate(total=Sum("quantity"))["total"] or Decimal("0")


class DrugInteraction(models.Model):
    """Tabella delle interazioni note, curata dal coordinatore/medico della struttura."""

    class Severity(models.TextChoices):
        MINOR = "minor", "Lieve"
        MODERATE = "moderate", "Moderata"
        MAJOR = "major", "Grave"

    ingredient_a = models.CharField("principio attivo A", max_length=150)
    ingredient_b = models.CharField("principio attivo B", max_length=150)
    severity = models.CharField("gravità", max_length=10, choices=Severity.choices, default=Severity.MODERATE)
    description = models.TextField("descrizione / indicazioni")
    source = models.CharField("fonte", max_length=255, blank=True)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="validata da", on_delete=models.PROTECT,
                                     null=True, blank=True, related_name="+")
    validated_at = models.DateTimeField("validata il", null=True, blank=True)

    class Meta:
        verbose_name = "interazione farmacologica"
        verbose_name_plural = "interazioni farmacologiche"
        ordering = ["ingredient_a", "ingredient_b"]
        permissions = [("validate_druginteraction", "Può validare le interazioni (medico della struttura)")]

    def __str__(self):
        return f"{self.ingredient_a} ↔ {self.ingredient_b}"

    @property
    def is_validated(self):
        return self.validated_at is not None

    def validation(self):
        if not self.is_validated:
            return "DA VALIDARE (non usata nei promemoria)"
        return f"validata da {self.validated_by} il {timezone.localtime(self.validated_at):%d/%m/%Y}"
    validation.short_description = "validazione"

    def row_action(self, user):
        if not self.is_validated and user.has_perm("pharmacy.validate_druginteraction"):
            from django.urls import reverse

            return reverse("pharmacy:interaction_validate", args=[self.pk]), "Valida"
        return None


class StockLot(models.Model):
    drug = models.ForeignKey(Drug, verbose_name="farmaco", on_delete=models.PROTECT, related_name="lots")
    guest = models.ForeignKey(
        "guests.Guest", verbose_name="ospite intestatario", on_delete=models.PROTECT, null=True, blank=True,
        related_name="stock_lots", help_text="Vuoto = scorta della comunità; altrimenti farmaco personale dell'ospite",
    )
    lot_number = models.CharField("lotto", max_length=60)
    expiry_date = models.DateField("scadenza")
    quantity = models.DecimalField("quantità", max_digits=10, decimal_places=2)
    received_on = models.DateField("data carico", default=timezone.localdate)
    supplier = models.CharField("fornitore / provenienza", max_length=150, blank=True)
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta:
        verbose_name = "lotto"
        verbose_name_plural = "magazzino farmaci"
        ordering = ["drug__name", "expiry_date"]

    def __str__(self):
        return f"{self.drug} – lotto {self.lot_number} (scad. {self.expiry_date:%d/%m/%Y})"

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        LOAD = "load", "Carico"
        ADMINISTRATION = "administration", "Scarico per somministrazione"
        ADJUSTMENT = "adjustment", "Rettifica inventario"
        DISPOSAL = "disposal", "Smaltimento (scaduto/deteriorato)"
        RETURN = "return", "Reso / restituzione"
        REVERSAL = "reversal", "Storno somministrazione annullata"

    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    quantity = models.DecimalField("quantità", max_digits=10, decimal_places=2, help_text="Positiva = carico, negativa = scarico")
    balance_after = models.DecimalField("giacenza dopo", max_digits=10, decimal_places=2)
    created_at = models.DateTimeField("data e ora", default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    administration = models.ForeignKey(
        "clinical.TherapyAdministration", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements"
    )
    notes = models.CharField("note", max_length=255, blank=True)

    class Meta:
        verbose_name = "movimento di magazzino"
        verbose_name_plural = "movimenti di magazzino"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.quantity} – {self.lot}"


class OfficialPackage(models.Model):
    """Confezione dall'elenco ufficiale dei medicinali (open data AIFA, CC BY 4.0). Solo consultazione: si sostituisce
    per intero a ogni caricamento e non tocca i farmaci già inseriti nel FASAS."""

    aic = models.CharField("codice AIC", max_length=9, unique=True)
    name = models.CharField("medicinale", max_length=200, db_index=True)
    description = models.CharField("confezione", max_length=300, blank=True)
    holder = models.CharField("titolare AIC", max_length=200, blank=True)
    atc = models.CharField("ATC", max_length=10, blank=True)
    ingredients = models.CharField("principio attivo", max_length=300, blank=True)
    form = models.CharField("forma", max_length=120, blank=True)
    status = models.CharField("stato", max_length=60, blank=True)

    class Meta:
        verbose_name = "confezione dell'elenco ufficiale"
        verbose_name_plural = "elenco ufficiale dei medicinali"
        ordering = ["name", "description"]
        permissions = [("import_official_list", "Può caricare l'elenco ufficiale dei medicinali")]

    def __str__(self):
        return f"{self.name} {self.description}".strip()

    def as_json(self):
        return {"aic": self.aic, "name": self.name, "description": self.description, "holder": self.holder,
                "atc": self.atc, "ingredients": self.ingredients, "form": self.form, "status": self.status}


class OfficialListImport(models.Model):
    created_at = models.DateTimeField("caricato il", default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    source_name = models.CharField("file", max_length=200)
    packages = models.PositiveIntegerField("confezioni")
    skipped = models.PositiveIntegerField("righe scartate", default=0)
    sha256 = models.CharField("impronta del file", max_length=64)

    class Meta:
        verbose_name = "caricamento dell'elenco ufficiale"
        verbose_name_plural = "caricamenti dell'elenco ufficiale"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Elenco ufficiale del {timezone.localtime(self.created_at):%d/%m/%Y} ({self.packages} confezioni)"
