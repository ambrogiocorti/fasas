"""
Copia continua sul disco di continuità: un disco esterno (SSD USB) sempre collegato al server.

Ogni 5 minuti: copia cifrata del database (stesso formato dei backup, ripristinabile con gli stessi strumenti)
e copia dei file nuovi o cambiati (già cifrati uno per uno). Se il disco interno del server si guasta si perdono
al massimo pochi minuti di registrazioni invece di un'intera giornata.

Il disco non protegge da furto, incendio o ransomware sul server stesso (è collegato e nello stesso locale):
per quelli restano la copia notturna fuori sede, non cancellabile, e la copia mensile su disco scollegato.

Il disco va preparato una volta con scripts/disco_continuita.sh, che scrive il file marcatore: se il disco non è
collegato la cartella resta vuota, la copia si ferma con un errore chiaro e non riempie per sbaglio il disco interno.
"""
import datetime
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .crypto import encrypt_stream
from .services import BackupError, build_archive, restore_backup

try:
    import fcntl
except ImportError:  # Windows (solo sviluppo): niente blocco tra due copie contemporanee
    fcntl = None

logger = logging.getLogger("fasas.backups")

MARKER = ".fasas-continuita"
STATUS = "ultima-copia.json"
PREFIX = "fasas-continua-"
MIN_FREE_BYTES = 2 * 1024 ** 3


class ContinuityError(Exception):
    pass


def is_configured():
    return bool(getattr(settings, "FASAS_CONTINUITY_DIR", ""))


def root():
    """Cartella del disco di continuità, solo se il disco preparato è davvero collegato."""
    path = Path(settings.FASAS_CONTINUITY_DIR)
    if not (path / MARKER).is_file():
        raise ContinuityError("Disco di continuità non collegato o non preparato: ricollegarlo al server "
                              "(guida d'installazione, passo 14b).")
    return path


def _stamp(moment):
    return timezone.localtime(moment).strftime("%Y%m%d-%H%M%S")


def _parse(name):
    try:
        naive = datetime.datetime.strptime(name[len(PREFIX):len(PREFIX) + 15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None
    return timezone.make_aware(naive)


def copies(base=None):
    """Copie del database presenti sul disco, dalla più recente: [(momento, percorso)]."""
    folder = (base or root()) / "database"
    found = [(_parse(p.name), p) for p in folder.glob(f"{PREFIX}*.fbk")] if folder.exists() else []
    return sorted([item for item in found if item[0] is not None], key=lambda item: item[0], reverse=True)


def _sync_media(source, target):
    """Copia i file nuovi o cambiati; non cancella nulla (i documenti non si eliminano)."""
    copied = 0
    if not source.exists():
        return copied
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        dest = target / path.relative_to(source)
        stat = path.stat()
        if dest.exists():
            current = dest.stat()
            if current.st_size == stat.st_size and int(current.st_mtime) >= int(stat.st_mtime):
                continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".parziale")
        shutil.copy2(path, partial)
        os.replace(partial, dest)
        copied += 1
    return copied


def _prune(folder, now):
    """Tutte le copie delle ultime ore; poi una per ora fino ai giorni indicati; le altre si cancellano."""
    keep_all = now - datetime.timedelta(hours=settings.FASAS_CONTINUITY_KEEP_HOURS)
    keep_hourly = now - datetime.timedelta(days=settings.FASAS_CONTINUITY_KEEP_DAYS)
    hours_seen, removed = set(), 0
    for moment, path in copies(folder.parent):
        if moment >= keep_all:
            continue
        hour = timezone.localtime(moment).strftime("%Y%m%d%H")
        if moment >= keep_hourly and hour not in hours_seen:
            hours_seen.add(hour)
            continue
        path.unlink(missing_ok=True)
        removed += 1
    for leftover in folder.glob("*.parziale"):
        if leftover.stat().st_mtime < (now - datetime.timedelta(hours=1)).timestamp():
            leftover.unlink(missing_ok=True)
    return removed


def continuous_copy(now=None):
    """Job ogni 5 minuti. Senza disco configurato non fa nulla; con il disco scollegato si ferma con un errore."""
    if not is_configured():
        return {"enabled": False}
    now = now or timezone.now()
    try:
        base = root()
        if shutil.disk_usage(base).free < MIN_FREE_BYTES:
            raise ContinuityError("Disco di continuità quasi pieno: meno di 2 GB liberi.")
        db_folder = base / "database"
        db_folder.mkdir(parents=True, exist_ok=True)
        with open(base / ".lock", "w") as lock:
            try:
                if fcntl is not None:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"enabled": True, "skipped": "copia precedente ancora in corso"}
            target = db_folder / f"{PREFIX}{_stamp(now)}.fbk"
            partial = target.with_name(target.name + ".parziale")
            with tempfile.TemporaryDirectory(prefix="fasas-continua-") as tmp:
                archive, db_format = build_archive(Path(tmp), now, include_media=False)
                with open(archive, "rb") as src, open(partial, "wb") as dst:
                    encrypt_stream(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
            os.chmod(partial, 0o600)
            os.replace(partial, target)
            media = _sync_media(Path(settings.MEDIA_ROOT), base / "media")
            removed = _prune(db_folder, now)
            status = {"at": now.isoformat(), "file": target.name, "size": target.stat().st_size,
                      "db_format": db_format, "media_copied": media}
            (base / STATUS).write_text(json.dumps(status), encoding="utf-8")
    except (ContinuityError, BackupError, OSError) as exc:
        from fasas.notifications.services import notify

        logger.error("Copia continua non riuscita: %s", type(exc).__name__)
        notify("backup", "Copia continua NON riuscita", str(exc)[:300], level="critical",
               dedup_key=f"continuity-{timezone.localtime(now):%Y%m%d%H}")
        raise
    return {"enabled": True, "file": target.name, "media_copied": media, "removed": removed}


def last_copy():
    """Momento dell'ultima copia riuscita (dal file di stato sul disco), oppure None."""
    try:
        data = json.loads((root() / STATUS).read_text(encoding="utf-8"))
        return datetime.datetime.fromisoformat(data["at"])
    except (ContinuityError, OSError, ValueError, KeyError):
        return None


def restore_latest(base=None, name=None, restore_media=True):
    """Ripristino dal disco di continuità: l'ultima copia (o quella indicata) e i file. Restituisce il momento."""
    base = Path(base) if base else root()
    if not (base / MARKER).is_file():
        raise ContinuityError(f"In {base} non c'è un disco di continuità preparato dal FASAS.")
    available = copies(base)
    if name:
        available = [item for item in available if item[1].name == name]
    if not available:
        raise ContinuityError("Nessuna copia del database sul disco di continuità.")
    moment, path = available[0]
    restore_backup(path, restore_media=False)
    if restore_media and (base / "media").exists():
        shutil.copytree(base / "media", settings.MEDIA_ROOT, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.parziale"))
    return moment, path
