"""
Struttura del modello Excel per importare il FASAS cartaceo.

Le stesse definizioni generano il modello scaricabile e validano il file compilato,
così intestazioni, elenchi a scelta e controlli non possono divergere.
"""
import datetime
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from fasas.clinical.models import Therapy
from fasas.guests.models import Allergy, Diagnosis, Guest, GuestContact
from fasas.pharmacy.models import Drug


class CellError(ValueError):
    pass


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def parse_text(value, column):
    text = _text(value)
    if column.max_length and len(text) > column.max_length:
        raise CellError(f"massimo {column.max_length} caratteri")
    return text


def parse_upper(value, column):
    return parse_text(value, column).upper().replace(" ", "")


def parse_date(value, column):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = _text(value)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CellError(f"data non valida «{text}» (usare GG/MM/AAAA)")


def parse_decimal(value, column):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = _text(value).replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise CellError(f"numero non valido «{_text(value)}»") from None


def parse_int(value, column):
    number = parse_decimal(value, column)
    if number is None:
        return None
    if number != number.to_integral_value() or number < 0:
        raise CellError("indicare un numero intero")
    return int(number)


YES = {"si", "sì", "s", "x", "1", "vero", "true", "yes", "y"}
NO = {"no", "n", "0", "falso", "false"}


def parse_bool(value, column):
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if not text:
        return None
    if text in YES:
        return True
    if text in NO:
        return False
    raise CellError(f"scrivere SI oppure NO (trovato «{_text(value)}»)")


TIME_RE = re.compile(r"^(\d{1,2})(?:[:.,h](\d{2}))?$")


def parse_times(value, column):
    """«08:00, 13 – 20.30» → ["08:00", "13:00", "20:30"]."""
    if value in (None, ""):
        return []
    if isinstance(value, datetime.time):
        return [value.strftime("%H:%M")]
    if isinstance(value, datetime.datetime):
        return [value.strftime("%H:%M")]
    times = []
    for part in re.split(r"[;,/\s–-]+", _text(value)):
        if not part:
            continue
        match = TIME_RE.match(part)
        if not match:
            raise CellError(f"orario non valido «{part}» (usare HH:MM separati da virgola)")
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if hour > 23 or minute > 59:
            raise CellError(f"orario non valido «{part}»")
        times.append(f"{hour:02d}:{minute:02d}")
    return sorted(set(times))


def parse_list(value, column):
    return [item.strip() for item in re.split(r"[,;]", _text(value)) if item.strip()]


@dataclass
class Column:
    key: str
    header: str
    required: bool = False
    parser: object = parse_text
    choices: list = field(default_factory=list)  # [(codice, etichetta)]
    dropdown: list = field(default_factory=list)  # elenco a scelta nel modello senza conversione di codici
    help: str = ""
    width: int = 18
    max_length: int = 0
    default: object = None

    def parse(self, value):
        if self.choices:
            return self.parse_choice(value)
        result = self.parser(value, self)
        if result in (None, "", []) and self.default is not None:
            return self.default
        return result

    def parse_choice(self, value):
        text = _text(value)
        if not text:
            return self.default if self.default is not None else ""
        wanted = text.lower()
        for code, label in self.choices:
            if wanted in (str(code).lower(), label.lower()):
                return code
        raise CellError(f"valore «{text}» non previsto: scegliere tra {', '.join(label for _, label in self.choices)}")

    @property
    def labels(self):
        return [label for _, label in self.choices] or self.dropdown


@dataclass
class Sheet:
    name: str
    title: str
    description: str
    columns: list

    def column(self, key):
        return next(c for c in self.columns if c.key == key)


SI_NO = ["SI", "NO"]


def yes_no(key, header, default=False, width=12):
    return Column(key, header, parser=parse_bool, dropdown=SI_NO, default=default, width=width)


GUEST_CF = Column("guest_cf", "Codice fiscale ospite", True, parse_upper, width=20,
                  help="Lo stesso del foglio Ospiti (o di un ospite già presente nel sistema)")


def _choices(model_choices):
    return list(model_choices)


SHEETS = [
    Sheet("Ospiti", "Ospiti", "Una riga per ospite: anagrafica e dati sanitari generali.", [
        Column("fiscal_code", "Codice fiscale", True, parse_upper, width=20, help="16 caratteri"),
        Column("last_name", "Cognome", True, max_length=100),
        Column("first_name", "Nome", True, max_length=100),
        Column("sex", "Sesso", choices=_choices(Guest.Sex.choices), default=Guest.Sex.X, width=12),
        Column("birth_date", "Data di nascita", True, parse_date, help="GG/MM/AAAA", width=14),
        Column("birth_place", "Luogo di nascita", max_length=120),
        Column("health_card_number", "Tessera sanitaria", max_length=30),
        Column("residence_address", "Residenza – indirizzo", max_length=255, width=26),
        Column("residence_city", "Residenza – comune", max_length=120),
        Column("residence_zip", "CAP", max_length=10, width=8),
        Column("room", "Camera / posto letto", max_length=30, width=12),
        Column("admission_date", "Data ingresso", True, parse_date, help="GG/MM/AAAA", width=14),
        Column("general_practitioner", "Medico curante", max_length=150, width=22),
        Column("general_practitioner_phone", "Telefono medico curante", max_length=50),
        Column("general_practitioner_email", "Email medico curante", max_length=254, width=22),
        Column("referring_service", "Servizio inviante / ente pagante", max_length=200, width=26),
        Column("disability_description", "Disabilità", width=30),
        Column("disability_certifications", "Certificazioni (L.104, invalidità %)", max_length=255, width=24),
        Column("diet", "Dieta", max_length=255, width=20),
        Column("diet_texture", "Consistenza alimenti", max_length=100, help="Es. normale, tritata, frullata"),
        Column("clinical_notes", "Note cliniche generali", width=36),
        Column("tags", "Tag clinici", parser=parse_list, width=24,
               help="Separati da virgola, es. Diabetico, Rischio caduta"),
    ]),
    Sheet("Contatti", "Contatti", "Familiari, tutori, amministratori di sostegno, assistenti sociali.", [
        GUEST_CF,
        Column("kind", "Tipo", True, choices=_choices(GuestContact.Kind.choices), width=24),
        Column("name", "Nome e cognome", True, max_length=150, width=22),
        Column("relationship", "Relazione / parentela", max_length=100),
        Column("phone", "Telefono", max_length=50),
        Column("email", "Email", max_length=254, width=22),
        Column("address", "Indirizzo", max_length=255, width=24),
        Column("legal_reference", "Decreto di nomina", max_length=150, help="Per tutori e amministratori di sostegno"),
        yes_no("is_emergency_contact", "Da contattare in emergenza"),
        yes_no("can_receive_health_info", "Può ricevere informazioni sanitarie"),
        Column("notes", "Note", width=24),
    ]),
    Sheet("Diagnosi", "Diagnosi", "Diagnosi e patologie in atto o rilevanti.", [
        GUEST_CF,
        Column("kind", "Tipo", choices=_choices(Diagnosis.Kind.choices), default=Diagnosis.Kind.DIAGNOSIS, width=12),
        Column("description", "Descrizione", True, max_length=255, width=34),
        Column("icd_code", "Codice ICD", max_length=20, width=12),
        Column("diagnosed_on", "Data", parser=parse_date, width=14),
        yes_no("is_primary", "Principale"),
        yes_no("active", "Attiva", default=True),
        Column("notes", "Note", width=24),
    ]),
    Sheet("Allergie", "Allergie", "Allergie e intolleranze. Per i farmaci indicare il principio attivo.", [
        GUEST_CF,
        Column("kind", "Tipo", choices=_choices(Allergy.Kind.choices), default=Allergy.Kind.ALLERGY, width=14),
        Column("category", "Categoria", choices=_choices(Allergy.Category.choices), default=Allergy.Category.DRUG,
               width=14),
        Column("substance", "Sostanza / principio attivo", True, max_length=150, width=24),
        Column("reaction", "Reazione", max_length=255, width=24),
        Column("severity", "Gravità", choices=_choices(Allergy.Severity.choices), default=Allergy.Severity.MODERATE,
               width=18),
        Column("notes", "Note", width=24),
    ]),
    Sheet("Terapie", "Terapie in corso", "Solo le terapie attive alla data di passaggio, come dal foglio unico di terapia.", [
        GUEST_CF,
        Column("drug_name", "Farmaco (nome commerciale)", True, max_length=150, width=24),
        Column("active_ingredient", "Principio attivo", True, max_length=150, width=22,
               help="Serve per i controlli di duplicati, interazioni e allergie"),
        Column("strength", "Dosaggio confezione", max_length=60, help="Es. 500 mg", width=14),
        Column("form", "Forma", choices=_choices(Drug.Form.choices), default=Drug.Form.TABLET, width=16),
        Column("dose", "Dose", True, parse_decimal, help="Numero, es. 1 o 0,5", width=8),
        Column("dose_unit", "Unità dose", max_length=30, default="cp", help="cp, mg, ml, gtt, UI...", width=10),
        Column("stock_units_per_dose", "Unità di magazzino per dose", parser=parse_decimal, default=Decimal("1"),
               help="Es. 0,5 per mezza compressa", width=12),
        Column("route", "Via", choices=_choices(Therapy.Route.choices), default=Therapy.Route.ORAL, width=16),
        Column("schedule_times", "Orari", parser=parse_times, help="Es. 08:00, 20:00 – vuoto per gli SOS", width=16),
        Column("every_n_days", "Ogni quanti giorni", parser=parse_int, default=1, help="1 = tutti i giorni", width=10),
        Column("start_date", "Inizio", True, parse_date, width=14),
        Column("end_date", "Fine", parser=parse_date, width=14),
        Column("instructions", "Istruzioni", width=28, help="Es. a stomaco pieno, frantumabile"),
        yes_no("is_sos", "Al bisogno (SOS)"),
        Column("sos_indication", "Indicazione SOS", max_length=255, width=24),
        Column("sos_max_daily", "SOS: massimo in 24 ore", parser=parse_int, width=10),
        Column("sos_min_interval_hours", "SOS: intervallo minimo (ore)", parser=parse_int, width=10),
        Column("prescriber_name", "Medico prescrittore", True, max_length=150, width=22),
        Column("prescription_date", "Data prescrizione", parser=parse_date, width=14),
    ]),
    Sheet("Magazzino", "Giacenze iniziali", "Farmaci presenti in struttura alla data di passaggio, per lotto.", [
        Column("drug_name", "Farmaco (nome commerciale)", True, max_length=150, width=24),
        Column("active_ingredient", "Principio attivo", max_length=150, width=22,
               help="Obbligatorio se il farmaco non è già in anagrafica o nel foglio Terapie"),
        Column("strength", "Dosaggio confezione", max_length=60, width=14),
        Column("form", "Forma", choices=_choices(Drug.Form.choices), default=Drug.Form.TABLET, width=16),
        Column("stock_unit", "Unità di magazzino", max_length=30, default="unità", help="compresse, ml, fiale..."),
        Column("lot_number", "Lotto", True, max_length=60, width=14),
        Column("expiry_date", "Scadenza", True, parse_date, width=14),
        Column("quantity", "Quantità", True, parse_decimal, width=10),
        Column("owner_cf", "Codice fiscale ospite (farmaco personale)", parser=parse_upper, width=20,
               help="Vuoto = scorta della comunità"),
        Column("supplier", "Fornitore / provenienza", max_length=150, width=20),
    ]),
]

SHEET_BY_NAME = {sheet.name.lower(): sheet for sheet in SHEETS}
