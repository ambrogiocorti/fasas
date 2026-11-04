"""
Moduli accendibili uno per uno (Configurazione › Moduli).

Un modulo spento sparisce dal menu e dai cruscotti, le sue pagine rispondono «funzione spenta» e i suoi promemoria
e controlli periodici non partono. I dati restano dove sono: riaccendendolo si ritrova tutto.

Il nucleo (ospiti, terapie e giro farmaci, parametri, eventi, diario, consegne, checklist, chiusura turni,
evacuazioni, documenti, notifiche, modalità senza rete, audit, backup, utenti) non si spegne.
"""
from dataclasses import dataclass
from functools import wraps


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    description: str
    namespaces: tuple = ()
    url_names: tuple = ()       # pagine singole ("namespace:nome") quando il namespace contiene anche il nucleo
    exempt: tuple = ()          # pagine del namespace che restano sempre attive
    jobs: tuple = ()            # job periodici (fasas.core.jobs) che non partono a modulo spento
    pilot: bool = True          # acceso nella «configurazione per il pilota»


MODULES = (
    Module("pai", "PAI", "Piani assistenziali individualizzati con obiettivi, verifiche e revisioni.",
           namespaces=("pai",), jobs=("pai_reviews",), pilot=False),
    Module("assessments", "Scale di valutazione", "Scale (es. Barthel, Braden, Norton) con le rivalutazioni.",
           namespaces=("assessments",), jobs=("assessments",), pilot=False),
    Module("wounds", "Lesioni e medicazioni", "Lesioni da pressione, piani di medicazione e scadenze.",
           namespaces=("wounds",), jobs=("wounds",), pilot=False),
    Module("protocols", "Protocolli automatici", "Protocolli che si attivano da soli su parametri, eventi, SOS ed "
           "evacuazioni.", namespaces=("protocols",), jobs=("protocols",), pilot=False),
    Module("appointments", "Appuntamenti", "Visite ed esami degli ospiti con promemoria.",
           namespaces=("appointments",), jobs=("appointments",), pilot=False),
    Module("stock", "Magazzino farmaci", "Lotti, scadenze e scorte. L'elenco dei farmaci per le terapie resta sempre "
           "attivo.", url_names=("pharmacy:stock", "pharmacy:lot_load", "pharmacy:lot_detail"), jobs=("stock",),
           pilot=False),
    Module("imports", "Importazione dal cartaceo", "Caricamento di ospiti e documenti dal FASAS cartaceo.",
           namespaces=("imports",), pilot=False),
    Module("staffing", "Turni del personale", "Calendario mensile, ferie e cambi turno.", namespaces=("staffing",)),
    Module("billing", "Presenze e rette", "Presenze per la rendicontazione, rette e prospetti.",
           namespaces=("billing",)),
    Module("reports", "Report e pacchetto per l'ispezione", "Report periodici, programmati e il pacchetto per la "
           "vigilanza. L'esportazione della cartella di un ospite resta sempre attiva.",
           namespaces=("reports",), exempt=("reports:guest_export",), jobs=("reports",)),
    Module("feedback", "Segnalazioni e indicatori del pilota", "Pulsante «Segnala un problema» per tutti e, per "
           "coordinatore e amministratore, le segnalazioni ricevute e gli indicatori (giro farmaci, registrazioni "
           "mancanti, checklist).", namespaces=("feedback",)),
    Module("remote_signature", "Firma remota qualificata", "Firma presso un prestatore qualificato (a pagamento). "
           "Serve anche la configurazione del prestatore sul server.", pilot=False),
)
BY_KEY = {m.key: m for m in MODULES}
PILOT_OFF = frozenset(m.key for m in MODULES if not m.pilot)
_BY_URL = {name: m for m in MODULES for name in m.url_names}
_BY_NAMESPACE = {ns: m for m in MODULES for ns in m.namespaces}
_BY_JOB = {job: m for m in MODULES for job in m.jobs}


def disabled(config=None):
    if config is None:
        from .models import SystemConfig

        config = SystemConfig.get()
    return {key for key in (config.disabled_modules or []) if key in BY_KEY}


def is_on(key, config=None):
    return key not in disabled(config)


def states(config=None):
    off = disabled(config)
    return {m.key: m.key not in off for m in MODULES}


def for_view(namespace, url_name):
    """Modulo a cui appartiene una pagina (None = nucleo, sempre attivo)."""
    full = f"{namespace}:{url_name}"
    if full in _BY_URL:
        return _BY_URL[full]
    module = _BY_NAMESPACE.get(namespace)
    if module is None or full in module.exempt:
        return None
    return module


def for_job(name):
    return _BY_JOB.get(name)


def when_on(key, default=None):
    """Decoratore: a modulo spento la funzione non fa nulla e restituisce default (eventi, promemoria)."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not is_on(key):
                return default() if callable(default) else default
            return func(*args, **kwargs)
        return wrapper
    return decorator
