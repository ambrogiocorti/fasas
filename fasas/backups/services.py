"""
Backup automatici cifrati (sezione 19).

Contenuto dell'archivio (tar.gz, poi cifrato AES-256-GCM):
- manifest.json con versione, data e SHA-256 di ogni componente;
- database.dump (pg_dump formato custom) su PostgreSQL, oppure database.json (dumpdata) negli altri casi;
- media.tar con i file caricati (già cifrati singolarmente).
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
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

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
    target = workdir / "database.json"
    with open(target, "w", encoding="utf-8") as handle:
        call_command("dumpdata", natural_foreign=True, natural_primary=False, exclude=DUMPDATA_EXCLUDE,
                     indent=None, stdout=handle)
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
            db_file, db_format = _dump_database(workdir)
            parts = [db_file]
            if include_media:
                parts.append(_media_tar(workdir))
            manifest = {
                "application": "FASAS Digitale",
                "created_at": record.created_at.isoformat(),
                "db_format": db_format,
                "db_vendor": connection.vendor,
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
            result = subprocess.run(
                ["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction",
                 "--dbname", settings.DATABASES["default"]["NAME"], str(workdir / "database.dump")],
                env=_pg_env(), capture_output=True, text=True, timeout=3600,
            )
            if result.returncode != 0:
                raise BackupError(f"pg_restore fallito: {result.stderr.strip()[:500]}")
        else:
            call_command("loaddata", str(workdir / "database.json"))
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


def scheduled_backup():
    record = create_backup(BackupRecord.Kind.AUTO)
    if record.status == BackupRecord.Status.OK:
        verify_backup(record)
    removed = purge_old_backups()
    return {"backup": record.pk, "status": record.status, "verified": record.verify_ok, "purged": removed}
