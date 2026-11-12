"""
Caricamento massivo dei documenti scansionati del FASAS cartaceo.

Ogni file viene abbinato all'ospite cercando nel percorso il codice fiscale
(es. «RSSMRA80A01F205X consenso.pdf») oppure una cartella o un nome file «Cognome Nome»
(es. «Rossi Mario/diario 2024.pdf»). L'abbinamento si controlla e si corregge in anteprima
prima di salvare; fino alla conferma i file restano cifrati in un'area temporanea.
"""
import datetime
import os
import re
import unicodedata
import zipfile

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from fasas.audit.context import audit_context
from fasas.core.encryption import read_encrypted, sha256, store_encrypted
from fasas.core.models import SystemConfig
from fasas.documents.services import create_document
from fasas.guests.models import Guest

from .models import ImportBatch

CF_RE = re.compile(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]")
SKIP_PARTS = ("__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini")


class DocumentImportError(Exception):
    pass


def _plain(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z]+", " ", text).upper().split())


def _name_index(guests):
    index = {}
    for guest in guests:
        for key in (f"{guest.last_name} {guest.first_name}", f"{guest.first_name} {guest.last_name}"):
            index.setdefault(_plain(key), set()).add(guest)
    return index


def match_guest(path, by_cf, by_name):
    upper = path.upper()
    for code in CF_RE.findall(upper):
        if code in by_cf:
            return by_cf[code]
    parts = [p for p in re.split(r"[\\/]", path) if p]
    for part in reversed(parts):
        stem = _plain(os.path.splitext(part)[0])
        for key, guests in by_name.items():
            if len(guests) == 1 and (stem == key or stem.startswith(key + " ")):
                return next(iter(guests))
    return None


def suggest_title(path, guest):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(CF_RE.pattern, "", stem, flags=re.IGNORECASE)
    if guest is not None:
        for name in (f"{guest.last_name} {guest.first_name}", f"{guest.first_name} {guest.last_name}"):
            stem = re.sub(re.escape(name), "", stem, flags=re.IGNORECASE)
    title = " ".join(re.sub(r"[_\-.]+", " ", stem).split()).strip()
    return (title[:1].upper() + title[1:]) if title else "Documento cartaceo scansionato"


def _files_from_upload(uploaded_files):
    """(percorso, contenuto) dai file caricati; gli archivi ZIP vengono aperti."""
    config = SystemConfig.get()
    max_bytes = config.max_upload_mb * 1024 * 1024
    zip_limit = getattr(settings, "FASAS_IMPORT_MAX_ZIP_MB", 1024) * 1024 * 1024
    for uploaded in uploaded_files:
        name = uploaded.name
        if name.lower().endswith(".zip"):
            try:
                archive = zipfile.ZipFile(uploaded)
            except zipfile.BadZipFile:
                yield name, None, "archivio ZIP non leggibile"
                continue
            total = 0
            for info in archive.infolist():
                if info.is_dir() or any(part in info.filename for part in SKIP_PARTS) \
                        or os.path.basename(info.filename).startswith("."):
                    continue
                total += info.file_size
                if total > zip_limit:
                    yield info.filename, None, "archivio troppo grande: dividerlo in più parti"
                    break
                if info.file_size > max_bytes:
                    yield info.filename, None, f"file oltre {config.max_upload_mb} MB"
                    continue
                yield info.filename, archive.read(info), ""
        else:
            if uploaded.size > max_bytes:
                yield name, None, f"file oltre {config.max_upload_mb} MB"
                continue
            yield name, uploaded.read(), ""


def _files_from_folder(folder):
    config = SystemConfig.get()
    max_bytes = config.max_upload_mb * 1024 * 1024
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_PARTS]
        for filename in sorted(files):
            if filename.startswith(".") or filename in SKIP_PARTS:
                continue
            full = os.path.join(root, filename)
            rel = os.path.relpath(full, folder)
            if os.path.getsize(full) > max_bytes:
                yield rel, None, f"file oltre {config.max_upload_mb} MB"
                continue
            with open(full, "rb") as fh:
                yield rel, fh.read(), ""


def prepare_batch(files, user, category, document_date=None, label=""):
    """Crea l'anteprima: cifra i file in un'area temporanea e propone ospite e titolo per ciascuno."""
    config = SystemConfig.get()
    allowed = config.extensions
    guests = list(Guest.objects.exclude(status=Guest.Status.ARCHIVED))
    by_cf = {g.fiscal_code: g for g in guests}
    by_name = _name_index(guests)
    entries = []
    for path, data, problem in files:
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if not problem and ext not in allowed:
            problem = f"estensione .{ext} non ammessa"
        if not problem and not data:
            problem = "file vuoto"
        guest = match_guest(path, by_cf, by_name) if not problem else None
        entry = {"path": path, "size": len(data or b""), "guest_id": guest.pk if guest else None,
                 "title": suggest_title(path, guest), "problem": problem, "storage": "", "sha256": ""}
        if not problem:
            entry["storage"] = store_encrypted(data, "imports")
            entry["sha256"] = sha256(data)
        entries.append(entry)
    if not entries:
        raise DocumentImportError("Nessun file trovato.")
    return ImportBatch.objects.create(
        kind=ImportBatch.Kind.DOCUMENTS, filename=label or f"{len(entries)} file", created_by=user,
        payload=entries, summary={"category": category,
                                  "document_date": document_date.isoformat() if document_date else ""},
    )


def prepare_from_upload(uploaded_files, user, category, document_date=None):
    names = ", ".join(f.name for f in uploaded_files[:3]) + ("…" if len(uploaded_files) > 3 else "")
    return prepare_batch(_files_from_upload(uploaded_files), user, category, document_date, names)


def prepare_from_folder(folder, user, category, document_date=None):
    return prepare_batch(_files_from_folder(folder), user, category, document_date, os.path.basename(folder))


def _discard(entries):
    for entry in entries:
        if entry.get("storage"):
            default_storage.delete(entry["storage"])
            entry["storage"] = ""


def confirm_batch(batch, user, choices=None):
    """
    Salva i documenti. choices = {indice: (guest_id o None, titolo)} dalle correzioni in anteprima;
    i file senza ospite vengono scartati.
    """
    entries = batch.payload
    category = batch.summary.get("category") or "other"
    document_date = batch.summary.get("document_date") or None
    if document_date:
        document_date = datetime.date.fromisoformat(document_date)
    guests = {g.pk: g for g in Guest.objects.exclude(status=Guest.Status.ARCHIVED)}
    created = skipped = 0
    with audit_context(user=user, source="import", reason="Caricamento documenti scansionati del FASAS cartaceo"):
        with transaction.atomic():
            for index, entry in enumerate(entries):
                if choices is not None and index in choices:
                    entry["guest_id"], entry["title"] = choices[index]
                guest = guests.get(entry.get("guest_id"))
                if entry["problem"] or guest is None or not entry["storage"]:
                    skipped += 1
                    entry["result"] = "scartato"
                    continue
                data = read_encrypted(entry["storage"])
                if sha256(data) != entry["sha256"]:
                    raise DocumentImportError(f"Il file {entry['path']} è stato alterato nell'area temporanea.")
                document = create_document(guest, category, (entry["title"] or "Documento")[:200], user=user,
                                           data=data, filename=os.path.basename(entry["path"]),
                                           document_date=document_date,
                                           description=f"Importato dal cartaceo: {entry['path']}")
                entry["result"] = "importato"
                entry["document_id"] = document.pk
                created += 1
            batch.status = ImportBatch.Status.COMPLETED
            batch.completed_at = timezone.now()
            batch.summary = {**batch.summary, "created": created, "skipped": skipped}
    _discard(entries)
    batch.payload = entries
    batch.save()
    return created, skipped


def cancel_batch(batch):
    _discard(batch.payload)
    batch.status = ImportBatch.Status.CANCELLED
    batch.completed_at = timezone.now()
    batch.save()


def cleanup_stale(hours=48):
    """Le anteprime abbandonate non lasciano file sanitari nell'area temporanea."""
    limit = timezone.now() - datetime.timedelta(hours=hours)
    count = 0
    for batch in ImportBatch.objects.filter(status=ImportBatch.Status.PREVIEW, created_at__lt=limit):
        if batch.kind == ImportBatch.Kind.DOCUMENTS:
            _discard(batch.payload)
        elif batch.payload:
            for name in batch.payload:
                default_storage.delete(name)
            batch.payload = []
        batch.status = ImportBatch.Status.CANCELLED
        batch.completed_at = timezone.now()
        batch.save()
        count += 1
    return {"cancelled": count}
