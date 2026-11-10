import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import read_encrypted, sha256, store_encrypted
from fasas.core.uploads import UploadError, clean_pdf_or_photo

from .models import CashMovement


class CashError(Exception):
    pass


def clean_receipt(uploaded):
    """Scontrino: foto JPEG/PNG (ridotta, senza dati EXIF) oppure PDF. Restituisce (byte, tipo)."""
    try:
        return clean_pdf_or_photo(uploaded)
    except UploadError as exc:
        raise CashError(str(exc)) from None


def balance(guest, until=None):
    movements = CashMovement.objects.filter(guest=guest)
    if until is not None:
        movements = movements.filter(occurred_on__lte=until)
    return movements.balance()


@transaction.atomic
def add_movement(guest, user, kind, amount, description, occurred_on=None, counterpart="", receipt=None):
    from fasas.guests.models import Guest

    guest = Guest.objects.select_for_update().get(pk=guest.pk)  # due movimenti insieme non sforano il saldo
    occurred_on = occurred_on or timezone.localdate()
    amount = Decimal(amount)
    if guest.is_archived:
        raise CashError("La cartella dell'ospite è archiviata: non si registrano movimenti.")
    if kind not in CashMovement.Kind.values:
        raise CashError("Tipo di movimento non previsto.")
    if amount <= 0:
        raise CashError("L'importo deve essere maggiore di zero.")
    if occurred_on > timezone.localdate():
        raise CashError("La data è nel futuro.")
    if not description.strip():
        raise CashError("Indicare la descrizione.")
    if kind != CashMovement.Kind.DEPOSIT:
        available = balance(guest)
        if amount > available:
            raise CashError(f"Saldo insufficiente: disponibili {available:.2f} €.")
    movement = CashMovement(guest=guest, kind=kind, amount=amount, description=description.strip(),
                            occurred_on=occurred_on, counterpart=counterpart.strip(), created_by=user)
    if receipt is not None:
        data, content_type = clean_receipt(receipt)
        movement.receipt_storage = store_encrypted(data, f"cassa/{guest.pk}")
        movement.receipt_sha256, movement.receipt_type = sha256(data), content_type
    movement.save()
    return movement


@transaction.atomic
def void_movement(movement, user, reason):
    if movement.is_voided:
        raise CashError("Movimento già annullato.")
    if not reason.strip():
        raise CashError("Indicare il motivo dell'annullamento.")
    if movement.kind == CashMovement.Kind.DEPOSIT and balance(movement.guest) - movement.amount < 0:
        raise CashError("Annullando questo versamento il saldo andrebbe sotto zero: annullare prima le spese.")
    movement.voided_at, movement.voided_by, movement.void_reason = timezone.now(), user, reason.strip()[:255]
    movement.save(update_fields=["voided_at", "voided_by", "void_reason", "updated_at"])
    return movement


def read_receipt(movement, user):
    data = read_encrypted(movement.receipt_storage)
    if sha256(data) != movement.receipt_sha256:
        raise CashError("Lo scontrino non corrisponde all'impronta registrata: possibile alterazione.")
    log_event(AuditLog.Action.DOWNLOAD, movement, user=user, guest=movement.guest)
    return data


def statement(guest, start, end):
    """Rendiconto di un periodo: saldo iniziale, movimenti validi, totali, saldo finale."""
    opening = balance(guest, start - datetime.timedelta(days=1))
    rows = list(CashMovement.objects.valid().filter(guest=guest, occurred_on__range=(start, end))
                .order_by("occurred_on", "created_at").select_related("created_by"))
    inflow = sum((m.amount for m in rows if m.kind == CashMovement.Kind.DEPOSIT), Decimal("0"))
    outflow = sum((m.amount for m in rows if m.kind != CashMovement.Kind.DEPOSIT), Decimal("0"))
    running, lines = opening, []
    for movement in rows:
        running += movement.signed_amount
        lines.append((movement, running))
    return {"opening": opening, "lines": lines, "inflow": inflow, "outflow": outflow,
            "closing": opening + inflow - outflow}


def statement_pdf(guest, start, end, user):
    from fasas.reports.pdf import Document, fmt

    data = statement(guest, start, end)
    doc = Document(f"Rendiconto della cassa personale – {guest.last_name} {guest.first_name}",
                   f"Periodo dal {start:%d/%m/%Y} al {end:%d/%m/%Y}", generated_by=user)
    doc.key_values([("Ospite", f"{guest.last_name} {guest.first_name}"), ("Codice fiscale", guest.fiscal_code),
                    ("Saldo al " + (start - datetime.timedelta(days=1)).strftime("%d/%m/%Y"), f"{data['opening']:.2f} €"),
                    ("Entrate del periodo", f"{data['inflow']:.2f} €"), ("Uscite del periodo", f"{data['outflow']:.2f} €"),
                    ("Saldo al " + end.strftime("%d/%m/%Y"), f"{data['closing']:.2f} €")])
    doc.heading("Movimenti")
    doc.table(["Data", "Tipo", "Descrizione", "Da / a", "Entrata", "Uscita", "Saldo", "Scontrino"], [
        [fmt(m.occurred_on), m.get_kind_display(), m.description, m.counterpart,
         f"{m.amount:.2f}" if m.kind == CashMovement.Kind.DEPOSIT else "",
         f"{m.amount:.2f}" if m.kind != CashMovement.Kind.DEPOSIT else "", f"{running:.2f}",
         "sì" if m.receipt_storage else ""]
        for m, running in data["lines"]] or [["", "Nessun movimento nel periodo", "", "", "", "", "", ""]],
        col_widths=[9, 12, 30, 14, 9, 9, 9, 8])
    doc.text("Il presente rendiconto riporta i movimenti registrati nel FASAS; gli scontrini sono conservati "
             "in forma cifrata e consultabili su richiesta.", "small")
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer

    doc.add(Spacer(0, 12 * mm))
    doc.text("Il responsabile della struttura ______________________________")
    doc.add(Spacer(0, 8 * mm))
    doc.text("Il tutore / amministratore di sostegno ______________________________")
    log_event(AuditLog.Action.EXPORT, guest, user=user, guest=guest,
              changes={"rendiconto cassa": [None, f"{start:%d/%m/%Y} - {end:%d/%m/%Y}"]})
    return doc.build()


def balances(guests):
    totals = {}
    for row in (CashMovement.objects.valid().filter(guest__in=guests).values("guest_id", "kind")
                .annotate(total=Sum("amount"))):
        sign = 1 if row["kind"] == CashMovement.Kind.DEPOSIT else -1
        totals[row["guest_id"]] = totals.get(row["guest_id"], Decimal("0")) + sign * row["total"]
    return totals
