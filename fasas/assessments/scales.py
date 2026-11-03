"""
Scale di valutazione: voci, punteggi, fasce e frequenza di rivalutazione predefinita.

Il FASAS registra il punteggio che l'operatore sceglie per ogni voce, ne fa la somma e riporta la fascia come
sulla scheda cartacea della scala. Le descrizioni sono brevi: per la valutazione si usa la scheda ufficiale
della scala adottata dalla struttura (alcune scale, es. Braden, sono protette da diritti: verificarne l'uso).
Non propone diagnosi né interventi: la fascia è un dato della scheda, la valutazione clinica resta dell'équipe.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    options: tuple  # ((punti, descrizione breve), ...)
    hint: str = ""


@dataclass(frozen=True)
class Band:
    low: int
    high: int
    label: str
    level: str  # ok | warn | danger


@dataclass(frozen=True)
class Scale:
    code: str
    name: str
    purpose: str
    items: tuple
    bands: tuple
    interval_days: int  # 0 = solo al bisogno
    enabled_by_default: bool = True
    note: str = ""
    keys: dict = field(default_factory=dict, compare=False)

    @property
    def max_total(self):
        return sum(max(p for p, _ in item.options) for item in self.items)

    @property
    def min_total(self):
        return sum(min(p for p, _ in item.options) for item in self.items)

    def band_for(self, total):
        for band in self.bands:
            if band.low <= total <= band.high:
                return band
        return None


def _levels(*labels):
    return tuple((points, label) for points, label in labels)


def _range(maximum, low="", high=""):
    """Voci a punteggio 0..max: descrizione agli estremi, come sulla scheda."""
    options = []
    for points in range(maximum + 1):
        text = low if points == 0 and low else high if points == maximum and high else ""
        options.append((points, f"{points}" + (f" – {text}" if text else "")))
    return tuple(options)


BARTHEL = Scale(
    code="barthel", name="Indice di Barthel", purpose="Autonomia nelle attività della vita quotidiana",
    note="Più alto = più autonomo (0–100).", interval_days=180,
    items=(
        Item("feeding", "Alimentazione", _levels((0, "dipendente"), (5, "ha bisogno di aiuto (tagliare, spalmare)"),
                                                 (10, "autonomo"))),
        Item("bathing", "Fare il bagno o la doccia", _levels((0, "dipendente"), (5, "autonomo"))),
        Item("grooming", "Igiene personale (viso, capelli, denti, rasatura)", _levels((0, "ha bisogno di aiuto"),
                                                                                    (5, "autonomo"))),
        Item("dressing", "Vestirsi", _levels((0, "dipendente"), (5, "ha bisogno di aiuto, fa circa metà da solo"),
                                             (10, "autonomo"))),
        Item("bowels", "Controllo intestinale", _levels((0, "incontinente"), (5, "incidenti occasionali"),
                                                        (10, "continente"))),
        Item("bladder", "Controllo vescicale", _levels((0, "incontinente o catetere non gestito"),
                                                       (5, "incidenti occasionali"), (10, "continente"))),
        Item("toilet", "Uso del WC", _levels((0, "dipendente"), (5, "ha bisogno di aiuto"), (10, "autonomo"))),
        Item("transfers", "Spostamento letto–sedia", _levels((0, "incapace"), (5, "grande aiuto (1–2 persone)"),
                                                             (10, "piccolo aiuto o supervisione"), (15, "autonomo"))),
        Item("mobility", "Deambulazione", _levels((0, "immobile"), (5, "autonomo in carrozzina"),
                                                  (10, "cammina con l'aiuto di una persona"),
                                                  (15, "autonomo, anche con ausili"))),
        Item("stairs", "Scale", _levels((0, "incapace"), (5, "ha bisogno di aiuto"), (10, "autonomo"))),
    ),
    bands=(Band(0, 20, "dipendenza totale", "danger"), Band(21, 60, "dipendenza grave", "danger"),
           Band(61, 90, "dipendenza moderata", "warn"), Band(91, 99, "dipendenza lieve", "ok"),
           Band(100, 100, "autonomo", "ok")),
)

_FOUR = ("1", "2", "3", "4")

BRADEN = Scale(
    code="braden", name="Scala di Braden", purpose="Rischio di lesioni da pressione",
    note="Più basso = rischio maggiore (6–23). Usare le descrizioni della scheda ufficiale.", interval_days=30,
    items=(
        Item("sensory", "Percezione sensoriale", _levels((1, "completamente limitata"), (2, "molto limitata"),
                                                         (3, "leggermente limitata"), (4, "nessuna limitazione"))),
        Item("moisture", "Umidità della pelle", _levels((1, "costantemente bagnata"), (2, "spesso bagnata"),
                                                        (3, "occasionalmente bagnata"), (4, "raramente bagnata"))),
        Item("activity", "Attività", _levels((1, "allettato"), (2, "in poltrona"), (3, "cammina occasionalmente"),
                                             (4, "cammina frequentemente"))),
        Item("mobility", "Mobilità", _levels((1, "completamente immobile"), (2, "molto limitata"),
                                             (3, "leggermente limitata"), (4, "nessuna limitazione"))),
        Item("nutrition", "Nutrizione", _levels((1, "molto scarsa"), (2, "probabilmente inadeguata"),
                                                (3, "adeguata"), (4, "eccellente"))),
        Item("friction", "Frizione e scivolamento", _levels((1, "problema"), (2, "problema potenziale"),
                                                            (3, "nessun problema apparente"))),
    ),
    bands=(Band(6, 9, "rischio molto alto", "danger"), Band(10, 12, "rischio alto", "danger"),
           Band(13, 14, "rischio moderato", "warn"), Band(15, 18, "rischio lieve", "warn"),
           Band(19, 23, "nessun rischio rilevato", "ok")),
)

NORTON = Scale(
    code="norton", name="Scala di Norton", purpose="Rischio di lesioni da pressione (alternativa alla Braden)",
    note="Più basso = rischio maggiore (5–20).", interval_days=30, enabled_by_default=False,
    items=(
        Item("condition", "Condizioni generali", _levels((1, "pessime"), (2, "scadenti"), (3, "discrete"), (4, "buone"))),
        Item("mental", "Stato mentale", _levels((1, "stuporoso"), (2, "confuso"), (3, "apatico"), (4, "lucido"))),
        Item("activity", "Attività", _levels((1, "costretto a letto"), (2, "costretto su sedia"),
                                             (3, "cammina con aiuto"), (4, "deambulante"))),
        Item("mobility", "Mobilità", _levels((1, "immobile"), (2, "molto limitata"), (3, "poco limitata"),
                                             (4, "piena"))),
        Item("incontinence", "Incontinenza", _levels((1, "doppia"), (2, "abituale (urine)"), (3, "occasionale"),
                                                     (4, "assente"))),
    ),
    bands=(Band(5, 11, "rischio alto", "danger"), Band(12, 14, "rischio medio", "warn"),
           Band(15, 20, "rischio basso", "ok")),
)

TINETTI = Scale(
    code="tinetti", name="Scala di Tinetti (POMA)", purpose="Equilibrio, andatura e rischio di caduta",
    note="Equilibrio 0–16 + andatura 0–12 = 0–28. Più basso = rischio di caduta maggiore.", interval_days=180,
    items=(
        Item("b_sitting", "Equilibrio – da seduto", _range(1, "si inclina o scivola", "stabile, sicuro")),
        Item("b_rise", "Equilibrio – alzarsi dalla sedia", _range(2, "incapace senza aiuto", "senza usare le braccia")),
        Item("b_attempts", "Equilibrio – tentativi di alzarsi", _range(2, "incapace senza aiuto", "un solo tentativo")),
        Item("b_immediate", "Equilibrio – primi 5 secondi in piedi", _range(2, "instabile", "stabile senza appoggi")),
        Item("b_standing", "Equilibrio – in piedi", _range(2, "instabile", "base stretta senza appoggi")),
        Item("b_nudge", "Equilibrio – spinta sullo sterno", _range(2, "inizia a cadere", "stabile")),
        Item("b_eyes", "Equilibrio – a occhi chiusi", _range(1, "instabile", "stabile")),
        Item("b_turn", "Equilibrio – girarsi di 360°", _range(2, "passi discontinui e instabile",
                                                              "passi continui e stabile")),
        Item("b_sit", "Equilibrio – sedersi", _range(2, "insicuro, cade sulla sedia", "sicuro, movimento fluido")),
        Item("g_start", "Andatura – inizio del cammino", _range(1, "esitazione o più tentativi", "nessuna esitazione")),
        Item("g_step", "Andatura – lunghezza e altezza del passo (dx e sx)", _range(4, "passi corti, piedi strisciati",
                                                                                     "passi regolari entrambi i lati")),
        Item("g_symmetry", "Andatura – simmetria del passo", _range(1, "asimmetrico", "simmetrico")),
        Item("g_continuity", "Andatura – continuità del passo", _range(1, "interruzioni", "continuo")),
        Item("g_path", "Andatura – traiettoria", _range(2, "deviazione marcata", "rettilinea senza ausili")),
        Item("g_trunk", "Andatura – tronco", _range(2, "oscillazioni o usa ausili", "stabile senza ausili")),
        Item("g_stance", "Andatura – base d'appoggio", _range(1, "talloni separati", "talloni quasi a contatto")),
    ),
    bands=(Band(0, 18, "rischio di caduta alto", "danger"), Band(19, 23, "rischio di caduta moderato", "warn"),
           Band(24, 28, "rischio di caduta basso", "ok")),
)

PAINAD = Scale(
    code="painad", name="PAINAD", purpose="Dolore in persone con difficoltà a comunicare",
    note="0–10. Osservazione per alcuni minuti; utile per persone con disabilità cognitiva.", interval_days=0,
    items=(
        Item("breathing", "Respiro", _levels((0, "normale"), (1, "occasionalmente difficoltoso, brevi iperventilazioni"),
                                             (2, "rumoroso e difficoltoso, lunghe iperventilazioni"))),
        Item("vocalization", "Vocalizzazione", _levels((0, "nessuna"), (1, "occasionali lamenti"),
                                                       (2, "lamenti ripetuti, grida, pianto"))),
        Item("face", "Espressione del volto", _levels((0, "sorridente o inespressiva"), (1, "triste, spaventata, accigliata"),
                                                      (2, "smorfie"))),
        Item("body", "Linguaggio del corpo", _levels((0, "rilassato"), (1, "teso, agitato, irrequieto"),
                                                     (2, "rigido, pugni serrati, ginocchia flesse, si allontana"))),
        Item("consolability", "Consolabilità", _levels((0, "non serve consolare"), (1, "si distrae o rassicura col contatto"),
                                                       (2, "non si riesce a consolare"))),
    ),
    bands=(Band(0, 0, "dolore assente", "ok"), Band(1, 3, "dolore lieve", "warn"),
           Band(4, 6, "dolore moderato", "danger"), Band(7, 10, "dolore grave", "danger")),
)

NRS = Scale(
    code="nrs", name="NRS – scala numerica del dolore", purpose="Dolore riferito dalla persona (0–10)",
    note="Per chi sa indicare un numero da 0 (nessun dolore) a 10 (il peggiore immaginabile).", interval_days=0,
    items=(Item("pain", "Intensità del dolore riferita", _range(10, "nessun dolore", "il peggiore immaginabile")),),
    bands=(Band(0, 0, "dolore assente", "ok"), Band(1, 3, "dolore lieve", "warn"),
           Band(4, 6, "dolore moderato", "danger"), Band(7, 10, "dolore grave", "danger")),
)

SCALES = {s.code: s for s in (BARTHEL, BRADEN, NORTON, TINETTI, PAINAD, NRS)}
SCALE_CHOICES = [(s.code, s.name) for s in SCALES.values()]


def get_scale(code):
    return SCALES[code]
