"""
Monitoraggio senza servizi esterni a pagamento.

- /salute/ risponde a un servizio di controllo (anche gratuito): 200 se tutto va, 503 se il database o i dischi
  non funzionano. Con FASAS_HEALTH_TOKEN (intestazione «Authorization: Bearer …» o ?token=) restituisce il
  dettaglio dei controlli: backup, verifica dell'audit, job periodici, spazio su disco, errori recenti.
- Gli errori del sistema finiscono in un registro raggruppato per punto del codice e l'amministratore riceve
  un avviso. Non si salvano messaggi, valori né dati delle richieste: solo tipo d'errore, rotta, righe di codice.
"""
import datetime
import hashlib
import logging
import shutil
import threading
import traceback
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

_local = threading.local()
PROJECT_ROOT = str(Path(settings.BASE_DIR).resolve())
NOTIFY_AT = {1, 10, 100, 1000}

# Ogni quanto deve girare ciascun job (minuti): oltre il doppio più mezz'ora è «in ritardo».
JOB_INTERVALS = {
    "close_shifts": 15, "protocols": 30, "appointments": 60, "stock": 12 * 60, "documents": 24 * 60,
    "pai_reviews": 24 * 60, "reports": 24 * 60, "report_retention": 24 * 60, "backup": 24 * 60,
    "audit_verify": 24 * 60, "imports_cleanup": 24 * 60, "cie_cleanup": 10, "restore_test": 95 * 24 * 60,
}


# --- Registro errori ----------------------------------------------------------------------------------

def _project_frames(tb):
    frames = []
    for frame in traceback.extract_tb(tb):
        filename = str(Path(frame.filename).resolve())
        if filename.startswith(PROJECT_ROOT) and "site-packages" not in filename:
            frames.append(f"{Path(filename).relative_to(PROJECT_ROOT)}:{frame.lineno} in {frame.name}")
    return frames[-10:]


def _where(record):
    request = getattr(record, "request", None)
    match = getattr(request, "resolver_match", None) if request is not None else None
    if match is not None:
        return f"{request.method} {match.route or match.view_name}"
    return f"{record.name}:{record.funcName}"


def record_error(record):
    from .models import ErrorEvent

    exc_type = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
    frames = _project_frames(record.exc_info[2]) if record.exc_info and record.exc_info[2] else []
    where = _where(record)[:255]
    template = str(record.msg)[:255]  # il modello del messaggio, senza gli argomenti che potrebbero contenere dati
    fingerprint = hashlib.sha256(f"{where}|{exc_type}|{frames[-1] if frames else template}".encode()).hexdigest()
    now = timezone.now()
    event, created = ErrorEvent.objects.get_or_create(fingerprint=fingerprint, defaults={
        "where": where, "exception": exc_type, "template": template, "frames": "\n".join(frames)})
    if not created:
        event.count += 1
        event.last_seen = now
        event.resolved_at = None
        event.save(update_fields=["count", "last_seen", "resolved_at"])
    if event.count in NOTIFY_AT:
        from fasas.notifications.services import notify

        notify("system_error", "Errore del sistema",
               f"{exc_type or 'Errore'} in {where} ({event.count} volt{'a' if event.count == 1 else 'e'}). "
               "Dettagli in Impostazioni › Errori di sistema.",
               link="/sistema/errori/", level="warning", dedup_key=f"error-{fingerprint}-{event.count}")
    return event


class ErrorRecordHandler(logging.Handler):
    """Handler di logging: registra gli errori senza mai interrompere la richiesta o il job che li ha causati."""

    def emit(self, record):
        if getattr(_local, "busy", False) or not getattr(settings, "FASAS_ERROR_RECORDING", True):
            return
        _local.busy = True
        try:
            record_error(record)
        except Exception:  # il database potrebbe essere proprio la causa dell'errore
            pass
        finally:
            _local.busy = False


# --- Job --------------------------------------------------------------------------------------------

def job_started(name):
    from .models import JobRun

    try:
        JobRun.objects.update_or_create(name=name, defaults={"last_started": timezone.now()})
    except Exception:  # il monitoraggio non deve impedire al job di girare
        pass


def job_finished(name, error=None):
    from django.db.models import F

    from .models import JobRun

    where = ""
    if error is not None:
        frames = _project_frames(error.__traceback__)
        where = f"{type(error).__name__}{' in ' + frames[-1] if frames else ''}"[:255]
    try:
        JobRun.objects.filter(name=name).update(last_finished=timezone.now(), last_ok=error is None,
                                                last_error=where, runs=F("runs") + 1)
    except Exception:
        pass


# --- Controllo di salute -------------------------------------------------------------------------------

def _writable(path):
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".fasas-salute"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except OSError:
        return False


def ping_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


def checks():
    """Elenco dei controlli: (nome, esito «ok» | «warning» | «error», descrizione senza dati sensibili)."""
    from fasas.audit.models import AuditCheckpoint
    from fasas.backups.models import BackupRecord

    from .models import ErrorEvent, JobRun

    now = timezone.now()
    results = []
    if not ping_database():
        return [("database", "error", "non raggiungibile")]
    results.append(("database", "ok", "raggiungibile"))
    for name, path in (("file", settings.MEDIA_ROOT), ("cartella_backup", settings.FASAS_BACKUP_DIR)):
        results.append((name, "ok" if _writable(path) else "error", "scrivibile" if _writable(path) else "non scrivibile"))
    free = shutil.disk_usage(Path(settings.MEDIA_ROOT)).free / 1024 ** 3
    level = "ok" if free >= settings.FASAS_HEALTH_MIN_FREE_GB else "warning"
    results.append(("spazio_disco", level, f"{free:.1f} GB liberi"))

    backup = BackupRecord.objects.filter(status=BackupRecord.Status.OK).first()
    if backup is None or backup.created_at < now - datetime.timedelta(hours=26):
        results.append(("backup", "warning", "nessun backup riuscito nelle ultime 26 ore"))
    elif backup.verify_ok is False:
        results.append(("backup", "warning", "ultimo backup non verificato"))
    else:
        results.append(("backup", "ok", f"ultimo {timezone.localtime(backup.created_at):%d/%m %H:%M}"))
    from fasas.backups import offsite

    if offsite.is_configured():
        copied = BackupRecord.objects.filter(offsite_at__isnull=False).order_by("-offsite_at").first()
        ok = copied is not None and copied.offsite_at > now - datetime.timedelta(hours=26)
        results.append(("backup_fuori_sede", "ok" if ok else "warning",
                        "copia delle ultime 26 ore presente" if ok else "nessuna copia fuori sede nelle ultime 26 ore"))

    checkpoint = AuditCheckpoint.objects.first()
    if checkpoint is None or checkpoint.created_at < now - datetime.timedelta(hours=26):
        results.append(("audit", "warning", "nessuna verifica nelle ultime 26 ore"))
    elif not checkpoint.chain_ok:
        results.append(("audit", "error", "audit log NON integro"))
    else:
        results.append(("audit", "ok", "integro" + (" con marca temporale" if checkpoint.timestamped else "")))

    runs = {run.name: run for run in JobRun.objects.all()}
    late, failed = [], []
    for name, minutes in JOB_INTERVALS.items():
        run = runs.get(name)
        if name == "restore_test" and run is None:
            continue  # trimestrale: la prima può non essere ancora arrivata
        if run is None or run.last_finished is None or run.last_finished < now - datetime.timedelta(minutes=2 * minutes + 30):
            late.append(name)
        elif run.last_ok is False:
            failed.append(name)
    if late or failed:
        detail = "; ".join(filter(None, [f"in ritardo o mai eseguiti: {', '.join(late)}" if late else "",
                                         f"falliti: {', '.join(failed)}" if failed else ""]))
        results.append(("job", "warning", detail))
    else:
        results.append(("job", "ok", "tutti eseguiti nei tempi"))

    recent = ErrorEvent.objects.filter(last_seen__gte=now - datetime.timedelta(hours=24), resolved_at__isnull=True)
    count = sum(recent.values_list("count", flat=True))
    results.append(("errori_24h", "ok" if not count else "warning", f"{count} errori in {recent.count()} punti del codice"))
    return results


def overall(results):
    states = {state for _, state, _ in results}
    return "error" if "error" in states else "degraded" if "warning" in states else "ok"
