"""
Prova di ripristino (consigliata ogni tre mesi, con verbale).

Prende il backup più recente (dalla copia fuori sede se configurata, altrimenti dal server), lo decifra,
controlla le impronte e lo ripristina davvero in un database separato, mai in quello in uso:
- backup JSON: un database SQLite temporaneo;
- backup PostgreSQL: il database vuoto indicato in FASAS_RESTORE_TEST_DATABASE_URL; se manca, si controlla
  solo che l'archivio pg_dump sia leggibile e il verbale lo dichiara «parziale».
Sul database ripristinato gira la verifica dell'audit log; il verbale riporta passaggi, esiti e conteggi.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from .models import BackupRecord, RestoreTest
from .services import BackupError, _decrypt_file, _sha256_file

COUNTED_TABLES = ["guests_guest", "clinical_therapy", "clinical_therapyadministration", "daily_diaryentry",
                  "documents_documentversion", "audit_auditlog", "accounts_user"]


def _manage(args, database_url, workdir, timeout=1800):
    env = os.environ.copy()
    env.update({"DATABASE_URL": database_url, "FASAS_BACKUP_DIR": str(workdir), "FASAS_MEDIA_ROOT": str(workdir / "media"),
                "FASAS_PUSH_ASYNC": "0"})
    return subprocess.run([sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), *args], env=env,
                          capture_output=True, text=True, timeout=timeout, cwd=settings.BASE_DIR)


def _pick_backup(workdir, steps):
    from . import offsite

    if offsite.is_configured():
        latest = next(iter(offsite.list_backups()), None)
        if latest:
            target = workdir / latest["name"]
            meta = offsite.download(latest["key"], target)
            steps.append(f"Scaricato dalla copia fuori sede: {latest['key']} ({latest['size']} byte).")
            if meta.get("sha256") and _sha256_file(target) != meta["sha256"]:
                raise BackupError("Il file scaricato non corrisponde all'impronta registrata al caricamento.")
            return target, "fuori sede", meta.get("sha256", "")
        steps.append("Copia fuori sede configurata ma vuota: si usa il backup sul server.")
    record = BackupRecord.objects.filter(status=BackupRecord.Status.OK, deleted_at__isnull=True).first()
    if record is None or not record.path or not record.path.exists():
        raise BackupError("Nessun backup disponibile da provare.")
    target = workdir / record.filename
    shutil.copy2(record.path, target)
    steps.append(f"Copiato dal server: {record.filename}.")
    return target, "locale", record.sha256


def _count_sqlite(path):
    db = sqlite3.connect(path)
    try:
        return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in COUNTED_TABLES}  # noqa: S608
    finally:
        db.close()  # su Windows un file aperto impedirebbe di cancellare la cartella temporanea


def _count_postgres(url):
    import psycopg

    with psycopg.connect(url) as db, db.cursor() as cursor:
        counts = {}
        for table in COUNTED_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - nomi fissi, non input
            counts[table] = cursor.fetchone()[0]
        return counts


def run_restore_test(user=None):
    started = time.monotonic()
    steps, counts, result, name, created = [], {}, RestoreTest.Result.FAILED, "", ""
    source = ""
    with tempfile.TemporaryDirectory(prefix="fasas-prova-ripristino-") as tmp:
        workdir = Path(tmp)
        try:
            path, source, expected = _pick_backup(workdir, steps)
            name = path.name
            archive = workdir / "backup.tar.gz"
            _decrypt_file(path, archive, expected)
            steps.append("Decifrato con la chiave di backup: autenticazione AES-256-GCM superata per ogni blocco.")
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(workdir / "contenuto", filter="data")
            manifest = json.loads((workdir / "contenuto" / "manifest.json").read_text())
            created = manifest.get("created_at", "")
            for part, meta in manifest["files"].items():
                if _sha256_file(workdir / "contenuto" / part) != meta["sha256"]:
                    raise BackupError(f"Componente {part} alterato.")
            steps.append(f"Impronte SHA-256 di {len(manifest['files'])} componenti corrispondenti al manifest.")

            if manifest["db_format"] == "json":
                database = workdir / "prova.sqlite3"
                url = f"sqlite:///{database.as_posix()}"
                restored = True
            elif settings.FASAS_RESTORE_TEST_DATABASE_URL:
                url, database, restored = settings.FASAS_RESTORE_TEST_DATABASE_URL, None, True
            else:
                listing = subprocess.run(["pg_restore", "--list", str(workdir / "contenuto" / "database.dump")],
                                         capture_output=True, text=True, timeout=600)
                if listing.returncode != 0:
                    raise BackupError(f"Archivio pg_dump illeggibile: {listing.stderr.strip()[:300]}")
                steps.append(f"Archivio pg_dump leggibile ({len(listing.stdout.splitlines())} voci). Ripristino del "
                             "database NON provato: impostare FASAS_RESTORE_TEST_DATABASE_URL (database vuoto).")
                restored, result = False, RestoreTest.Result.PARTIAL

            if restored:
                if manifest["db_format"] == "json":
                    migrate = _manage(["migrate", "--noinput"], url, workdir)
                    if migrate.returncode != 0:
                        raise BackupError(f"Preparazione del database di prova fallita: {migrate.stderr[-300:]}")
                restore = _manage(["backup_restore", str(path), "--confirm", "--no-media"], url, workdir)
                if restore.returncode != 0:
                    raise BackupError(f"Ripristino fallito: {(restore.stderr or restore.stdout)[-400:]}")
                steps.append("Database ripristinato in un database separato (quello in uso non è stato toccato).")
                audit = _manage(["audit_verify"], url, workdir)
                if audit.returncode != 0:
                    raise BackupError(f"Audit log del backup NON integro: {(audit.stderr or audit.stdout)[-300:]}")
                steps.append(audit.stdout.strip().splitlines()[-1] if audit.stdout.strip() else "Audit log integro.")
                counts = _count_sqlite(database) if database else _count_postgres(url)
                before = manifest.get("audit_entries_before_dump")
                if before is not None and counts["audit_auditlog"] < before:
                    raise BackupError(f"Mancano voci di audit: {counts['audit_auditlog']} invece di almeno {before}.")
                steps.append("Conteggi dei dati principali letti dal database ripristinato.")
                result = RestoreTest.Result.OK
        except Exception as exc:
            steps.append(f"ERRORE: {exc}")
            result = RestoreTest.Result.FAILED
    test = RestoreTest.objects.create(
        backup_name=name, backup_created_at=created, source=source, result=result, steps=steps, counts=counts,
        duration_seconds=int(time.monotonic() - started), created_by=user,
    )
    log_event(AuditLog.Action.RESTORE, test, user=user, changes={"prova_di_ripristino": [None, result]})
    if result == RestoreTest.Result.FAILED:
        from fasas.notifications.services import notify

        notify("backup", "Prova di ripristino FALLITA", steps[-1][:300], level="critical",
               dedup_key=f"restore-test-{test.pk}")
    return test


def scheduled_restore_test():
    test = run_restore_test()
    return {"test": test.pk, "result": test.result, "at": timezone.localtime(test.created_at).isoformat()}
