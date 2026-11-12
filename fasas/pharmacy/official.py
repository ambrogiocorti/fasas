"""
Elenco ufficiale delle confezioni di medicinali (open data AIFA, licenza CC BY 4.0: citare la fonte).

Il file si scarica dalla pagina «Open data» del sito AIFA e si carica nel FASAS (Impostazioni › Farmaci › Elenco
ufficiale, oppure «python manage.py fasas_farmaci_aifa file.csv»). Serve a compilare i farmaci senza errori di
battitura (nome, principio attivo, ATC, codice AIC) e a riconoscere la confezione con il lettore di codici a barre.

Le colonne si riconoscono dal nome, con le varianti usate nei file AIFA (CSV con «;» o «,», oppure Excel).
"""
import csv
import hashlib
import io
import re
import unicodedata

from django.db import transaction

COLUMNS = {
    "aic": ("codice_aic", "aic", "codice aic", "cod_aic", "codice_aic_confezione", "aic confezione"),
    "cod_farmaco": ("cod_farmaco", "codice_farmaco", "codice farmaco"),
    "cod_confezione": ("cod_confezione", "codice_confezione", "codice confezione"),
    "name": ("denominazione", "farmaco", "nome_farmaco", "nome farmaco", "denominazione farmaco", "medicinale",
             "nome commerciale"),
    "description": ("descrizione", "confezione", "descrizione_confezione", "descrizione confezione",
                    "denominazione e confezione"),
    "holder": ("ragione_sociale", "ditta", "titolare", "titolare aic", "titolare_aic", "azienda"),
    "atc": ("codice_atc", "atc", "cod_atc", "codice atc"),
    "ingredients": ("pa_associati", "principio_attivo", "principio attivo", "principi attivi", "principi_attivi",
                    "sostanza attiva"),
    "form": ("forma", "forma_farmaceutica", "forma farmaceutica"),
    "status": ("stato_amministrativo", "stato", "stato amministrativo"),
}
MAX_ROWS = 400_000


class OfficialListError(Exception):
    pass


def _key(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[\s_.\-/]+", " ", text).strip()


def _index(header):
    keys = [_key(h) for h in header]
    found = {}
    for field, names in COLUMNS.items():
        for name in names:
            if _key(name) in keys:
                found[field] = keys.index(_key(name))
                break
    return found


def normalize_aic(value):
    """Codice AIC di confezione: 9 cifre (gli zeri iniziali contano). Restituisce "" se non è un AIC."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits or len(digits) > 9:
        return ""
    return digits.zfill(9)


def aic_in_code(code, aic):
    """True se il codice letto dal lettore (bollino, Data Matrix, digitato) contiene il codice AIC della confezione."""
    aic = normalize_aic(aic)
    digits = re.sub(r"\D", "", str(code or ""))
    return bool(aic) and aic in digits


def _rows_from_bytes(data, filename):
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        yield from (["" if c is None else str(c) for c in row] for row in sheet.iter_rows(values_only=True))
        return
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise OfficialListError("File non leggibile: serve un CSV (UTF-8 o Windows) o un file Excel.")
    first = text[:5000]
    delimiter = max(";,|\t", key=first.count)
    yield from csv.reader(io.StringIO(text), delimiter=delimiter)


def parse(data, filename="elenco.csv"):
    """Righe del file come dizionari normalizzati; scarta le righe senza un AIC valido. Cerca l'intestazione nelle
    prime 20 righe (alcuni file hanno un titolo sopra la tabella)."""
    rows = _rows_from_bytes(data, filename)
    index = None
    for _ in range(20):
        try:
            header = next(rows)
        except StopIteration:
            break
        index = _index(header)
        if "name" in index and ("aic" in index or {"cod_farmaco", "cod_confezione"} <= set(index)):
            break
        index = None
    if index is None:
        raise OfficialListError("Intestazione non riconosciuta: servono almeno le colonne del codice AIC e della "
                                "denominazione del medicinale.")

    def cell(row, field):
        position = index.get(field)
        return row[position].strip() if position is not None and position < len(row) and row[position] else ""

    packages, skipped = {}, 0
    for row in rows:
        if not any(row):
            continue
        aic = normalize_aic(cell(row, "aic"))
        if not aic and cell(row, "cod_farmaco") and cell(row, "cod_confezione"):
            aic = normalize_aic(cell(row, "cod_farmaco").zfill(6) + cell(row, "cod_confezione").zfill(3))
        name = cell(row, "name")
        if not aic or not name:
            skipped += 1
            continue
        packages[aic] = {
            "aic": aic, "name": name[:200], "description": cell(row, "description")[:300],
            "holder": cell(row, "holder")[:200], "atc": cell(row, "atc").upper().replace(" ", "")[:10],
            "ingredients": cell(row, "ingredients")[:300], "form": cell(row, "form")[:120],
            "status": cell(row, "status")[:60],
        }
        if len(packages) > MAX_ROWS:
            raise OfficialListError(f"File troppo grande: più di {MAX_ROWS} confezioni.")
    if not packages:
        raise OfficialListError("Nessuna confezione con codice AIC trovata nel file.")
    return list(packages.values()), skipped


@transaction.atomic
def import_list(data, filename, user=None):
    """Sostituisce l'elenco ufficiale con quello del file. I farmaci già inseriti nel FASAS non cambiano."""
    from fasas.audit.models import AuditLog
    from fasas.audit.services import log_event

    from .models import OfficialListImport, OfficialPackage

    packages, skipped = parse(data, filename)
    OfficialPackage.objects.all().delete()
    OfficialPackage.objects.bulk_create((OfficialPackage(**p) for p in packages), batch_size=2000)
    record = OfficialListImport.objects.create(
        user=user, source_name=filename[:200], packages=len(packages), skipped=skipped,
        sha256=hashlib.sha256(data).hexdigest())
    log_event(AuditLog.Action.CONFIG, record, user=user, changes={"confezioni": [None, len(packages)]})
    return record


def search(query, limit=15):
    from django.db.models import Q

    from .models import OfficialPackage

    query = (query or "").strip()
    if len(query) < 3:
        return []
    digits = re.sub(r"\D", "", query)
    if digits and not re.search(r"[^\W\d_]{2,}", query):  # un codice (digitato o letto dal lettore), non un nome
        if len(digits) >= 9:
            qs = OfficialPackage.objects.filter(aic__in={digits[i:i + 9] for i in range(len(digits) - 8)})
        else:
            qs = OfficialPackage.objects.filter(aic__startswith=digits)
    else:
        qs = OfficialPackage.objects.all()
        for word in query.split()[:4]:
            qs = qs.filter(Q(name__icontains=word) | Q(ingredients__icontains=word) | Q(description__icontains=word))
    return list(qs.order_by("name", "description")[:limit])
