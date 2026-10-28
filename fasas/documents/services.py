import mimetypes
import os

from django.core.exceptions import ValidationError
from django.db import transaction

from fasas.audit.models import AuditLog, lock_audit_chain
from fasas.audit.services import log_event
from fasas.core.encryption import read_encrypted, sha256, store_encrypted
from fasas.core.models import SystemConfig
from fasas.guests.services import ensure_not_archived

from .models import Document, DocumentVersion


class IntegrityError(Exception):
    pass


def validate_upload(uploaded, config=None):
    config = config or SystemConfig.get()
    limit = config.max_upload_mb * 1024 * 1024
    if uploaded.size > limit:
        raise ValidationError(f"Il file supera la dimensione massima di {config.max_upload_mb} MB.")
    ext = os.path.splitext(uploaded.name)[1].lower().lstrip(".")
    if ext not in config.extensions:
        raise ValidationError(f"Estensione .{ext} non ammessa. Ammesse: {', '.join(sorted(config.extensions))}.")


def _guess_type(name, fallback="application/octet-stream"):
    return mimetypes.guess_type(name)[0] or fallback


@transaction.atomic
def add_version(document, data: bytes, original_name, user, note="", content_type=None, is_signed=False):
    ensure_not_archived(document.guest)
    lock_audit_chain()
    last = document.versions.select_for_update().order_by("-number").first()
    version = DocumentVersion.objects.create(
        document=document,
        number=(last.number + 1) if last else 1,
        storage_name=store_encrypted(data, f"documents/{document.guest_id}"),
        original_name=os.path.basename(original_name)[:255],
        content_type=content_type or _guess_type(original_name),
        size=len(data),
        sha256=sha256(data),
        note=note,
        uploaded_by=user,
        is_signed=is_signed,
    )
    log_event(
        AuditLog.Action.CREATE, version, guest=document.guest,
        changes={"versione": [None, version.number], "file": [None, version.original_name], "sha256": [None, version.sha256]},
    )
    return version


def add_uploaded_version(document, uploaded, user, note=""):
    validate_upload(uploaded)
    return add_version(document, uploaded.read(), uploaded.name, user, note, uploaded.content_type)


@transaction.atomic
def create_document(guest, category, title, uploaded=None, user=None, data=None, filename=None, **extra):
    ensure_not_archived(guest)
    document = Document.objects.create(guest=guest, category=category, title=title, **extra)
    if uploaded is not None:
        add_uploaded_version(document, uploaded, user)
    elif data is not None:
        add_version(document, data, filename or f"{title}.pdf", user, content_type=_guess_type(filename or ".pdf"))
    return document


def read_version(version, user=None, audit=True):
    """Decifra una versione verificandone l'integrità; ogni accesso è tracciato."""
    data = read_encrypted(version.storage_name)
    if sha256(data) != version.sha256:
        raise IntegrityError(f"Il file {version} non corrisponde all'impronta registrata: possibile alterazione.")
    if audit:
        log_event(AuditLog.Action.DOWNLOAD, version, user=user, guest=version.document.guest)
    return data


def expiry_alerts(today=None, days=30):
    """Job: documenti in scadenza (es. carta d'identità) nei prossimi giorni."""
    import datetime

    from django.utils import timezone

    from fasas.notifications.services import notify

    today = today or timezone.localdate()
    count = 0
    for document in Document.objects.filter(
        expires_on__isnull=False, expires_on__lte=today + datetime.timedelta(days=days),
    ).exclude(guest__status="archived").select_related("guest"):
        expired = document.expires_on < today
        notify(
            "document_expiring",
            f"{'Documento scaduto' if expired else 'Documento in scadenza'}: {document.title} – {document.guest}",
            f"Scadenza {document.expires_on:%d/%m/%Y}.",
            link=document.get_absolute_url(), guest=document.guest, level="warning" if expired else "info",
            dedup_key=f"doc-expiry-{document.pk}-{'expired' if expired else 'soon'}",
        )
        count += 1
    return {"documents": count}
