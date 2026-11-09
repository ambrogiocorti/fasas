"""
Orari dei job periodici e pianificatore integrato.

La tabella SCHEDULE è l'unica fonte degli orari: Celery beat la usa nell'installazione in struttura
(config/celery.py), il pianificatore integrato («manage.py fasas_pianificatore») nella versione cloud, dove non c'è
Redis. Gli orari sono nel fuso della struttura (Europe/Rome), con la sintassi di cron: «*», «*/15», «6,18», «1-5».

Il pianificatore integrato:
- ogni minuto esegue i job dovuti; se un job lungo (il backup) lo ha tenuto occupato, recupera i minuti saltati;
- all'avvio recupera i job che dovevano partire mentre il servizio era fermo (fino a 26 ore prima): un servizio di
  hosting che riavvia o addormenta il container non fa perdere il backup della notte;
- con più copie del servizio attive insieme (durante un aggiornamento) ogni esecuzione è «prenotata» nel database
  con un aggiornamento condizionato: un job parte una volta sola per ogni orario, qualunque copia arrivi prima.
"""
import datetime
import logging
import signal
import time

from django.db import IntegrityError, close_old_connections
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("fasas.jobs")

# nome, job (fasas.core.jobs.JOBS), orario come in cron (campi non indicati = «*»)
SCHEDULE = [
    ("chiusura-automatica-turni", "close_shifts", {"minute": "*/15"}),
    ("protocolli-periodici", "protocols", {"minute": "*/30"}),
    ("promemoria-appuntamenti", "appointments", {"minute": "5"}),
    ("allarmi-magazzino", "stock", {"hour": "6,18", "minute": "10"}),
    ("scadenze-documenti", "documents", {"hour": "7", "minute": "10"}),
    ("scadenze-pai", "pai_reviews", {"hour": "7", "minute": "0"}),
    ("scadenze-valutazioni", "assessments", {"hour": "7", "minute": "5"}),
    ("medicazioni-in-ritardo", "wounds", {"hour": "7", "minute": "10"}),
    ("report-programmati", "reports", {"hour": "1", "minute": "15"}),
    ("pulizia-report-scaduti", "report_retention", {"hour": "1", "minute": "45"}),
    ("gruppo-di-continuita", "ups", {}),
    ("copia-continua", "continuity", {"minute": "*/5"}),
    ("backup-giornaliero", "backup", {"hour": "2", "minute": "30"}),
    # prima del backup, così il backup e la sua copia fuori sede contengono il punto di controllo della notte
    ("verifica-catena-audit", "audit_verify", {"hour": "2", "minute": "0"}),
    ("prova-ripristino-trimestrale", "restore_test",
     {"hour": "4", "minute": "15", "day_of_month": "1", "month_of_year": "1,4,7,10"}),
    ("pulizia-importazioni", "imports_cleanup", {"hour": "3", "minute": "50"}),
    ("pulizia-firme-cie", "cie_cleanup", {"minute": "*/10"}),
]

# campo: (minimo, massimo)
FIELDS = {"minute": (0, 59), "hour": (0, 23), "day_of_month": (1, 31), "month_of_year": (1, 12), "day_of_week": (0, 6)}
CATCH_UP = datetime.timedelta(hours=26)  # all'avvio si recuperano i job dovuti nelle ultime 26 ore
# oltre (orologio spostato, processo sospeso a lungo) si riparte da adesso; più largo del recupero all'avvio
MAX_GAP = CATCH_UP + datetime.timedelta(hours=4)


def parse_field(spec, low, high):
    """Valori ammessi da un campo cron: «*», «*/n», «a», «a-b», «a-b/n», separati da virgole."""
    values = set()
    for part in str(spec).split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError(f"passo non valido: {spec}")
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
        else:
            start = int(part)
            end = high if step > 1 else start
        if not (low <= start <= end <= high):
            raise ValueError(f"valore fuori intervallo {low}-{high}: {spec}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


def compile_spec(spec):
    unknown = set(spec) - set(FIELDS)
    if unknown:
        raise ValueError(f"campi sconosciuti: {', '.join(sorted(unknown))}")
    return {name: parse_field(spec.get(name, "*"), low, high) for name, (low, high) in FIELDS.items()}


def matches(compiled, moment):
    """Vero se il minuto locale «moment» corrisponde all'orario (domenica = 0 come in cron)."""
    return (moment.minute in compiled["minute"] and moment.hour in compiled["hour"]
            and moment.day in compiled["day_of_month"] and moment.month in compiled["month_of_year"]
            and moment.isoweekday() % 7 in compiled["day_of_week"])


COMPILED = [(name, job, compile_spec(spec)) for name, job, spec in SCHEDULE]
# versione di presentazione: dati di prova ricreati a ogni avvio, niente backup né apparecchi della struttura
PRESENTATION_SKIPPED = {"backup", "restore_test", "continuity", "ups"}


def _skipped():
    from django.conf import settings

    return PRESENTATION_SKIPPED if settings.FASAS_PRESENTAZIONE else set()


MINUTE = datetime.timedelta(minutes=1)


def _utc_minute(moment):
    return moment.astimezone(datetime.timezone.utc).replace(second=0, microsecond=0)


def _wall(moment):
    return timezone.localtime(moment).replace(tzinfo=None)


def due(after, until):
    """
    Job dovuti nei minuti dopo «after» fino a «until» compreso: {job: minuto (UTC) in cui è diventato dovuto}.
    Un job dovuto più volte nell'intervallo si esegue una volta sola. Ogni minuto dell'orologio locale si valuta una
    volta: quando l'ora legale salta in avanti (02:00 → 03:00) i job delle 02:xx partono alle 03:00; quando torna
    indietro l'ora ripetuta fa ripartire solo i job che girano a ogni ora, non quelli giornalieri (backup…).
    """
    found = {}
    skipped = _skipped()
    moment = _utc_minute(after) + MINUTE
    last = _utc_minute(until)
    # ora locale più avanzata già raggiunta nell'ultima ora: dentro l'ora ripetuta è quella prima del ritorno indietro
    seen = max(_wall(moment - MINUTE * back) for back in range(1, 62))
    while moment <= last:
        local = _wall(moment)
        if local <= seen:  # ora ripetuta: ripartono solo i job che girano a ogni ora (turni, controlli frequenti)
            for _, job, compiled in COMPILED:
                if len(compiled["hour"]) == 24 and job not in skipped and matches(compiled, local):
                    found[job] = moment
        while seen < local:
            seen += MINUTE
            for _, job, compiled in COMPILED:
                if job not in skipped and matches(compiled, seen):
                    found[job] = moment
        moment += MINUTE
    return found


def claim(job, slot, now=None):
    """
    Prenota l'esecuzione di «job» per l'orario «slot»: vero solo per chi la ottiene. È un aggiornamento condizionato
    nel database, quindi funziona anche con più copie del servizio e con il pooler di connessioni di Supabase.
    """
    from .models import JobRun

    now = now or timezone.now()
    try:
        JobRun.objects.get_or_create(name=job)
    except IntegrityError:  # creato nello stesso istante da un'altra copia
        pass
    taken = JobRun.objects.filter(name=job).filter(Q(last_started__isnull=True) | Q(last_started__lt=slot))
    return taken.update(last_started=now) == 1


def run_due(after, until, runner=None):
    """Esegue i job dovuti nell'intervallo che nessun'altra copia ha già avviato. Restituisce i job eseguiti."""
    from .jobs import run_job

    runner = runner or run_job
    done = []
    for job, slot in sorted(due(after, until).items(), key=lambda item: item[1]):
        if not claim(job, slot):
            continue
        try:
            runner(job)
        except Exception:  # già registrato da run_job (registro errori e stato del job): si prosegue con gli altri
            logger.warning("Pianificatore: job %s non riuscito", job)
        finally:
            close_old_connections()
        done.append(job)
    return done


class Scheduler:
    """Ciclo del pianificatore: un controllo all'inizio di ogni minuto, fino a SIGTERM o SIGINT."""

    def __init__(self, runner=None, sleep=time.sleep, clock=timezone.now):
        self.runner, self.sleep, self.clock = runner, sleep, clock
        self.stopping = False

    def stop(self, *_):
        self.stopping = True

    def install_signals(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

    def tick(self, last):
        now = self.clock()
        if now - last > MAX_GAP or now < last:
            logger.warning("Pianificatore: salto dell'orologio (%s → %s), si riparte da adesso", last, now)
            last = now - datetime.timedelta(minutes=1)
        close_old_connections()
        try:
            run_due(last, now, self.runner)
        except Exception:  # database irraggiungibile o simili: si riprova al minuto successivo
            logger.exception("Pianificatore: controllo dei job non riuscito")
            close_old_connections()
            return last
        return now

    def run(self, once=False):
        last = self.clock() - CATCH_UP
        while not self.stopping:
            last = self.tick(last)
            if once:
                break
            now = self.clock()
            wait = 60 - now.second - now.microsecond / 1_000_000 + 1  # un secondo dopo l'inizio del minuto
            while wait > 0 and not self.stopping:
                step = min(wait, 5)
                self.sleep(step)
                wait -= step
