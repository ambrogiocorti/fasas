"""
Backup automatici cifrati (sezione 19).

Contenuto dell'archivio (tar.gz, poi cifrato AES-256-GCM):
- manifest.json con versione, data e SHA-256 di ogni componente;
- database.dump (pg_dump formato custom) su PostgreSQL, oppure database.json (dumpdata) negli altri casi;
- media.tar con i file caricati (già cifrati singolarmente);
- audit-punti-di-controllo.csv con i punti di controllo dell'audit (impronte e marche temporali).

Dopo la verifica il backup viene copiato fuori sede (fasas.backups.offsite) se è configurato un object storage.
"""
import datetime
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from fasas import __version__
from fasas.audit.anchoring import export_lines
from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.models import SystemConfig

from .crypto import decrypt_stream, encrypt_stream
from .models import BackupRecord

logger = logging.getLogger("fasas.backups")

DUMPDATA_EXCLUDE = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


class BackupError(Exception):
    pass


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pg_env():
    db = settings.DATABASES["default"]
    env = os.environ.copy()
    env.update({
        "PGHOST": str(db.get("HOST") or "localhost"),
        "PGPORT": str(db.get("PORT") or "5432"),
        "PGUSER": str(db.get("USER") or ""),
        "PGPASSWORD": str(db.get("PASSWORD") or ""),
        "PGDATABASE": str(db.get("NAME") or ""),
    })
    sslmode = (db.get("OPTIONS") or {}).get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = sslmode
    return env


def _dump_database(workdir):
    if connection.vendor == "postgresql" and shutil.which("pg_dump"):
        target = workdir / "database.dump"
        result = subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(target)],
            env=_pg_env(), capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            raise BackupError(f"pg_dump fallito: {result.stderr.strip()[:500]}")
        return target, "pg_dump"
    target = workdir / "database.fasasjson"  # JSON con orari esatti: l'audit ripristinato resta verificabile
    with open(target, "w", encoding="utf-8") as handle:
        call_command("dumpdata", format="fasasjson", natural_foreign=True, natural_primary=False,
                     exclude=DUMPDATA_EXCLUDE, indent=None, stdout=handle)
    return target, "json"


def _media_tar(workdir):
    media_root = Path(settings.MEDIA_ROOT)
    target = workdir / "media.tar"
    with tarfile.open(target, "w") as tar:
        if media_root.exists():
            tar.add(media_root, arcname="media")
    return target


def create_backup(kind=BackupRecord.Kind.AUTO, user=None, include_media=True):
    backup_dir = Path(settings.FASAS_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    record = BackupRecord.objects.create(kind=kind, created_by=user, includes_media=include_media)
    stamp = timezone.localtime(record.created_at).strftime("%Y%m%d-%H%M%S")
    filename = f"fasas-backup-{stamp}-{record.pk}.fbk"
    try:
        with tempfile.TemporaryDirectory(prefix="fasas-backup-") as tmp:
            workdir = Path(tmp)
            audit_entries = AuditLog.objects.count()
            db_file, db_format = _dump_database(workdir)
            parts = [db_file]
            if include_media:
                parts.append(_media_tar(workdir))
            checkpoints = workdir / "audit-punti-di-controllo.csv"
            checkpoints.write_text(export_lines(), encoding="utf-8")
            parts.append(checkpoints)
            manifest = {
                "application": "FASAS Digitale",
                "version": __version__,
                "created_at": record.created_at.isoformat(),
                "db_format": db_format,
                "db_vendor": connection.vendor,
                "audit_entries_before_dump": audit_entries,
                # numeri interni dei tipi di oggetto: il ripristino JSON li riporta uguali (vedi _align_content_types)
                "content_types": list(ContentType.objects.order_by("pk").values_list("pk", "app_label", "model")),
                "files": {p.name: {"sha256": _sha256_file(p), "size": p.stat().st_size} for p in parts},
            }
            archive = workdir / "backup.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                data = json.dumps(manifest, indent=2).encode()
                info = tarfile.TarInfo("manifest.json")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
                for part in parts:
                    tar.add(part, arcname=part.name)
            target = backup_dir / filename
            with open(archive, "rb") as src, open(target, "wb") as dst:
                encrypt_stream(src, dst)
            os.chmod(target, 0o600)
        record.filename = filename
        record.size = target.stat().st_size
        record.sha256 = _sha256_file(target)
        record.db_format = db_format
        record.status = BackupRecord.Status.OK
    except Exception as exc:
        logger.exception("Backup fallito")
        record.status = BackupRecord.Status.FAILED
        record.error = str(exc)[:2000]
    record.finished_at = timezone.now()
    record.save()
    log_event(AuditLog.Action.BACKUP, record, user=user,
              changes={"esito": [None, record.status], "file": [None, record.filename]})
    if record.status == BackupRecord.Status.FAILED:
        from fasas.notifications.services import notify

        notify("backup", "Backup FALLITO", record.error[:300], level="critical", dedup_key=f"backup-failed-{record.pk}")
    return record


def _decrypt_file(path, target_path, expected_sha256=""):
    if path is None or not Path(path).exists():
        raise BackupError("File di backup non trovato.")
    if expected_sha256 and _sha256_file(path) != expected_sha256:
        raise BackupError("Il file di backup non corrisponde all'impronta registrata.")
    with open(path, "rb") as src, open(target_path, "wb") as dst:
        decrypt_stream(src, dst)


def verify_backup(record):
    """Verifica integrità: impronta del file, decifratura completa e controllo del manifest."""
    try:
        with tempfile.TemporaryDirectory(prefix="fasas-verify-") as tmp:
            archive = Path(tmp) / "backup.tar.gz"
            _decrypt_file(record.path, archive, record.sha256)
            with tarfile.open(archive, "r:gz") as tar:
                manifest = json.load(tar.extractfile("manifest.json"))
                for name, meta in manifest["files"].items():
                    member = tar.extractfile(name)
                    digest = hashlib.sha256()
                    while block := member.read(1024 * 1024):
                        digest.update(block)
                    if digest.hexdigest() != meta["sha256"]:
                        raise BackupError(f"Componente {name} alterato.")
        record.verify_ok = True
        record.error = ""
    except Exception as exc:
        record.verify_ok = False
        record.error = f"Verifica fallita: {exc}"[:2000]
    record.verified_at = timezone.now()
    record.save(update_fields=["verify_ok", "verified_at", "error"])
    if not record.verify_ok:
        from fasas.notifications.services import notify

        notify("backup", "Verifica backup FALLITA", record.error[:300], level="critical",
               dedup_key=f"backup-verify-{record.pk}")
    return record.verify_ok


# Impostazioni scritte da pg_dump recenti che un server PostgreSQL più vecchio non conosce
# (pg_dump 17 aggiunge «SET transaction_timeout», che PostgreSQL 15 e 16 rifiutano).
NEWER_SERVER_SETTINGS = {17: ("SET transaction_timeout = 0;",)}


def _server_major():
    connection.ensure_connection()
    return connection.pg_version // 10000


def _pg_restore(dump):
    """Ripristino in un'unica transazione; verso server più vecchi del client si tolgono le impostazioni sconosciute."""
    database = settings.DATABASES["default"]["NAME"]
    options = ["--clean", "--if-exists", "--no-owner", "--no-privileges"]
    skip = {line for major, lines in NEWER_SERVER_SETTINGS.items() if _server_major() < major for line in lines}
    if not skip:
        result = subprocess.run(["pg_restore", *options, "--single-transaction", "--dbname", database, str(dump)],
                                env=_pg_env(), capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise BackupError(f"pg_restore fallito: {result.stderr.strip()[:500]}")
        return
    # pg_restore produce l'SQL, si filtrano le righe incompatibili e psql lo esegue in un'unica transazione.
    # Gli errori vanno su file temporanei: una pipe piena bloccherebbe i due processi.
    with tempfile.TemporaryFile() as source_err, tempfile.TemporaryFile() as target_err:
        source = subprocess.Popen(["pg_restore", *options, "--file", "-", str(dump)], env=_pg_env(),
                                  stdout=subprocess.PIPE, stderr=source_err)
        target = subprocess.Popen(["psql", "--quiet", "--no-psqlrc", "--single-transaction", "-v", "ON_ERROR_STOP=1",
                                   "--dbname", database], env=_pg_env(), stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=target_err)
        try:
            for line in source.stdout:
                if line.decode("utf-8", "replace").strip() not in skip:
                    target.stdin.write(line)
        except BrokenPipeError:  # psql si è fermato su un errore: il messaggio è nel suo file d'errore
            source.kill()
        finally:
            source.stdout.close()
            try:
                target.stdin.close()
            except BrokenPipeError:
                pass
        failed = source.wait(timeout=3600) != 0 or target.wait(timeout=3600) != 0
        if failed:
            target_err.seek(0)
            source_err.seek(0)
            message = (target_err.read() or source_err.read()).decode("utf-8", "replace").strip()
            raise BackupError(f"Ripristino fallito: {message[:500]}")


def _align_content_types(mapping):
    """
    In un database appena creato i tipi di oggetto possono avere numeri interni diversi dall'originale (l'ordine delle
    migrazioni cambia nel tempo). Le voci di audit con impronta versione 1 contengono quel numero: prima di caricare
    un backup JSON si riportano i numeri dell'originale, aggiornando anche le tabelle che li usano.
    """
    from django.apps import apps

    ContentType.objects.clear_cache()
    current = {(ct.app_label, ct.model): ct.pk for ct in ContentType.objects.all()}
    wanted = {(app_label, model): pk for pk, app_label, model in mapping}
    if all(current.get(key) == pk for key, pk in wanted.items() if key in current):
        return
    references = [(m._meta.db_table, f.column) for m in apps.get_models() for f in m._meta.concrete_fields
                  if f.is_relation and f.related_model is ContentType]
    quote = connection.ops.quote_name
    ct_table = quote(ContentType._meta.db_table)
    offset = max([*current.values(), *wanted.values()]) + 1000
    spare = iter(range(max(wanted.values()) + 1, offset))
    targets = {old: wanted.get(key) or next(spare) for key, old in current.items()}

    def move(cursor, old, new):  # nomi di tabella e colonna dai modelli, valori come parametri
        cursor.execute(f"UPDATE {ct_table} SET id = %s WHERE id = %s", [new, old])  # nosec B608
        for table, column in references:
            sql = f"UPDATE {quote(table)} SET {quote(column)} = %s WHERE {quote(column)} = %s"  # nosec B608
            cursor.execute(sql, [new, old])

    with transaction.atomic(), connection.constraint_checks_disabled(), connection.cursor() as cursor:
        for old in targets:  # prima tutti fuori dall'intervallo, così nessun numero si scontra
            move(cursor, old, old + offset)
        for old, new in targets.items():
            move(cursor, old + offset, new)
    ContentType.objects.clear_cache()


def restore_backup(path, restore_media=True):
    """
    Ripristino completo. Da usare solo da riga di comando (manage.py backup_restore) con
    l'applicazione ferma: sostituisce il contenuto del database.
    """
    with tempfile.TemporaryDirectory(prefix="fasas-restore-") as tmp:
        workdir = Path(tmp)
        archive = workdir / "backup.tar.gz"
        expected = ""
        if BackupRecord._meta.db_table in connection.introspection.table_names():  # il db di destinazione può essere vuoto
            record = BackupRecord.objects.filter(filename=Path(path).name).first()
            expected = record.sha256 if record else ""
        _decrypt_file(path, archive, expected)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(workdir, filter="data")
        manifest = json.loads((workdir / "manifest.json").read_text())
        for name, meta in manifest["files"].items():
            if _sha256_file(workdir / name) != meta["sha256"]:
                raise BackupError(f"Componente {name} alterato: ripristino annullato.")
        if manifest["db_format"] == "pg_dump":
            if connection.vendor != "postgresql":
                raise BackupError("Il backup è PostgreSQL: il database di destinazione deve essere PostgreSQL.")
            _pg_restore(workdir / "database.dump")
        else:
            dump = next(name for name in ("database.fasasjson", "database.json") if (workdir / name).exists())
            if manifest.get("content_types"):
                _align_content_types(manifest["content_types"])
            call_command("loaddata", str(workdir / dump))
        if restore_media and (workdir / "media.tar").exists():
            with tarfile.open(workdir / "media.tar") as media:
                media.extractall(workdir / "restored", filter="data")
            if (workdir / "restored" / "media").exists():
                shutil.copytree(workdir / "restored" / "media", settings.MEDIA_ROOT, dirs_exist_ok=True)
    return manifest


def purge_old_backups(today=None):
    days = SystemConfig.get().backup_retention_days
    limit = timezone.now() - datetime.timedelta(days=days)
    removed = 0
    for record in BackupRecord.objects.filter(created_at__lt=limit, deleted_at__isnull=True,
                                              status=BackupRecord.Status.OK):
        # si conserva sempre l'ultimo backup verificato
        if record == BackupRecord.objects.filter(status=BackupRecord.Status.OK, verify_ok=True).first():
            continue
        if record.path and record.path.exists():
            record.path.unlink()
        record.deleted_at = timezone.now()
        record.save(update_fields=["deleted_at"])
        removed += 1
    return removed


def copy_offsite(record):
    """Copia fuori sede di un backup verificato; un errore avvisa l'amministratore ma non tocca il backup locale."""
    from . import offsite

    if not offsite.is_configured() or record.status != BackupRecord.Status.OK or not record.verify_ok:
        return None
    try:
        key, until = offsite.upload_backup(record)
    except Exception as exc:
        logger.exception("Copia fuori sede fallita")
        record.offsite_error = f"{type(exc).__name__}: {exc}"[:2000]
        record.save(update_fields=["offsite_error"])
        from fasas.notifications.services import notify

        notify("backup", "Copia fuori sede del backup NON riuscita", record.offsite_error[:300], level="critical",
               dedup_key=f"backup-offsite-{record.pk}")
        return False
    record.offsite_key, record.offsite_at, record.offsite_locked_until, record.offsite_error = key, timezone.now(), until, ""
    record.save(update_fields=["offsite_key", "offsite_at", "offsite_locked_until", "offsite_error"])
    log_event(AuditLog.Action.BACKUP, record, changes={"copia_fuori_sede": [None, key]})
    return True


def scheduled_backup():
    from . import offsite

    record = create_backup(BackupRecord.Kind.AUTO)
    if record.status == BackupRecord.Status.OK:
        verify_backup(record)
    copied = copy_offsite(record)
    pruned = offsite.prune() if copied else None
    removed = purge_old_backups()
    return {"backup": record.pk, "status": record.status, "verified": record.verify_ok, "purged": removed,
            "offsite": copied, "offsite_pruned": pruned}
