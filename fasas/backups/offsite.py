"""
Copia dei backup fuori sede su object storage compatibile S3 in UE, con blocco delle modifiche (Object Lock).

- Ogni backup cifrato viene caricato subito dopo la verifica; il fornitore vede solo dati cifrati
  (la chiave FASAS_BACKUP_KEY resta alla struttura).
- Con Object Lock in modalità COMPLIANCE nessuno (nemmeno chi ha le credenziali, né un ransomware)
  può cancellare o sovrascrivere la copia prima di FASAS_OFFSITE_LOCK_DAYS giorni.
  Il bucket va creato con Object Lock attivo (si imposta solo alla creazione, dal pannello del fornitore).
- Conservazione: l'ultimo backup di ciascuno degli ultimi FASAS_OFFSITE_KEEP_DAILY giorni e di ciascuno
  degli ultimi FASAS_OFFSITE_KEEP_MONTHLY mesi; gli altri si cancellano quando il blocco è scaduto.
- Insieme al backup si caricano i punti di controllo dell'audit: una copia immutabile fuori dal server.

Nessun fornitore è preconfigurato: va scelto dalla struttura (contratto art. 28, data center in UE).
"""
import base64
import datetime
import hashlib
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("fasas.backups")


class OffsiteError(Exception):
    pass


def is_configured():
    return bool(settings.FASAS_OFFSITE_BUCKET and settings.FASAS_OFFSITE_ACCESS_KEY and settings.FASAS_OFFSITE_SECRET_KEY)


def client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.FASAS_OFFSITE_ENDPOINT or None,
        region_name=settings.FASAS_OFFSITE_REGION or None,
        aws_access_key_id=settings.FASAS_OFFSITE_ACCESS_KEY,
        aws_secret_access_key=settings.FASAS_OFFSITE_SECRET_KEY,
        config=Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=20, read_timeout=300,
                      request_checksum_calculation="when_required", response_checksum_validation="when_required"),
    )


def _key(name):
    prefix = settings.FASAS_OFFSITE_PREFIX.strip("/")
    return f"{prefix}/{name}" if prefix else name


def _lock_args():
    days = settings.FASAS_OFFSITE_LOCK_DAYS
    if days <= 0:
        return {}, None
    until = timezone.now() + datetime.timedelta(days=days)
    return {"ObjectLockMode": settings.FASAS_OFFSITE_LOCK_MODE, "ObjectLockRetainUntilDate": until}, until


def upload_file(path, name, metadata=None, s3=None):
    """Carica un file con il blocco delle modifiche e controlla dimensione e impronta lato fornitore."""
    s3 = s3 or client()
    key = _key(name)
    lock, until = _lock_args()
    size = Path(path).stat().st_size
    md5 = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as body:
        for block in iter(lambda: body.read(1024 * 1024), b""):
            md5.update(block)
    # Content-MD5: il fornitore rifiuta un caricamento arrivato alterato (e con Object Lock è obbligatorio)
    with open(path, "rb") as body:
        s3.put_object(Bucket=settings.FASAS_OFFSITE_BUCKET, Key=key, Body=body, Metadata=metadata or {},
                      ContentMD5=base64.b64encode(md5.digest()).decode(), **lock)
    head = s3.head_object(Bucket=settings.FASAS_OFFSITE_BUCKET, Key=key)
    if head["ContentLength"] != size:
        raise OffsiteError(f"Copia fuori sede incompleta: {head['ContentLength']} byte invece di {size}.")
    if metadata and head.get("Metadata", {}).get("sha256") not in (None, metadata.get("sha256")):
        raise OffsiteError("Copia fuori sede con impronta diversa.")
    return key, until


def upload_backup(record):
    """Copia fuori sede di un backup già verificato, più i punti di controllo dell'audit."""
    from fasas.audit.anchoring import export_lines

    s3 = client()
    key, until = upload_file(record.path, f"backup/{record.filename}",
                             {"sha256": record.sha256, "created": record.created_at.isoformat()}, s3=s3)
    stamp = timezone.localtime(record.created_at).strftime("%Y%m%d-%H%M%S")
    checkpoints = Path(settings.FASAS_BACKUP_DIR) / f".audit-{stamp}.csv"
    try:
        checkpoints.write_text(export_lines(), encoding="utf-8")
        upload_file(checkpoints, f"audit/punti-di-controllo-{stamp}.csv", s3=s3)
    finally:
        checkpoints.unlink(missing_ok=True)
    return key, until


def list_backups(s3=None):
    """Backup presenti fuori sede, dal più recente: [{"key", "name", "modified", "size"}]."""
    s3 = s3 or client()
    items = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=settings.FASAS_OFFSITE_BUCKET,
                                                               Prefix=_key("backup/")):
        for obj in page.get("Contents", []):
            items.append({"key": obj["Key"], "name": obj["Key"].rsplit("/", 1)[-1],
                          "modified": obj["LastModified"], "size": obj["Size"]})
    return sorted(items, key=lambda item: item["modified"], reverse=True)


def download(key, target, s3=None):
    s3 = s3 or client()
    s3.download_file(settings.FASAS_OFFSITE_BUCKET, key, str(target))
    head = s3.head_object(Bucket=settings.FASAS_OFFSITE_BUCKET, Key=key)
    return head.get("Metadata", {})


def retention_plan(items, now=None):
    """Chiavi da tenere: il più recente di ogni giorno (ultimi N giorni) e di ogni mese (ultimi M mesi)."""
    now = now or timezone.now()
    keep, days, months = set(), set(), set()
    for item in items:  # dal più recente
        local = timezone.localtime(item["modified"])
        day, month = local.date(), (local.year, local.month)
        if day not in days and (now.date() - day).days < settings.FASAS_OFFSITE_KEEP_DAILY:
            days.add(day)
            keep.add(item["key"])
        months_ago = (now.year - month[0]) * 12 + now.month - month[1]
        if month not in months and months_ago < settings.FASAS_OFFSITE_KEEP_MONTHLY:
            months.add(month)
            keep.add(item["key"])
    if items:
        keep.add(items[0]["key"])  # il più recente resta sempre
    return keep


def prune(s3=None):
    """
    Cancella i backup fuori sede non più da conservare. Con Object Lock il bucket è versionato: si cancellano
    le singole versioni; quelle ancora bloccate restano (il fornitore rifiuta) e si riprova la notte dopo.
    """
    s3 = s3 or client()
    bucket = settings.FASAS_OFFSITE_BUCKET
    keep = retention_plan(list_backups(s3))
    removed, locked = 0, 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=_key("backup/")):
        for version in page.get("Versions", []) + page.get("DeleteMarkers", []):
            if version["Key"] in keep:
                continue
            try:
                s3.delete_object(Bucket=bucket, Key=version["Key"], VersionId=version["VersionId"])
                removed += 1
            except Exception as exc:  # blocco non ancora scaduto: è il comportamento voluto
                locked += 1
                logger.info("Backup fuori sede %s non cancellabile ora: %s", version["Key"], type(exc).__name__)
    return {"removed": removed, "still_locked": locked, "kept": len(keep)}
