import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from fasas.audit.models import lock_audit_chain
from fasas.core.models import SystemConfig

from .models import Drug, StockLot, StockMovement


def _move(lot, kind, quantity, user=None, administration=None, notes=""):
    lot.quantity = lot.quantity + quantity
    lot.save(update_fields=["quantity"])
    return StockMovement.objects.create(
        lot=lot, kind=kind, quantity=quantity, balance_after=lot.quantity,
        created_by=user, administration=administration, notes=notes,
    )


@transaction.atomic
def load_lot(drug, lot_number, expiry_date, quantity, user, guest=None, supplier="", notes=""):
    lot = StockLot.objects.create(
        drug=drug, guest=guest, lot_number=lot_number, expiry_date=expiry_date,
        quantity=Decimal("0"), supplier=supplier, notes=notes,
    )
    _move(lot, StockMovement.Kind.LOAD, Decimal(quantity), user, notes=notes)
    return lot


@transaction.atomic
def adjust_lot(lot, new_quantity, user, kind=StockMovement.Kind.ADJUSTMENT, notes=""):
    lock_audit_chain()
    lot = StockLot.objects.select_for_update().get(pk=lot.pk)
    delta = Decimal(new_quantity) - lot.quantity
    if delta:
        _move(lot, kind, delta, user, notes=notes)
    return lot


def candidate_lots(drug, guest):
    """FEFO: prima i farmaci personali dell'ospite, poi la scorta comune; mai lotti scaduti."""
    today = timezone.localdate()
    lots = StockLot.objects.select_for_update().filter(
        drug=drug, quantity__gt=0, expiry_date__gte=today
    ).filter(Q(guest=guest) | Q(guest__isnull=True))
    return sorted(lots, key=lambda lot: (lot.guest_id is None, lot.expiry_date, lot.pk))


@transaction.atomic
def unload_for_administration(administration, quantity, user):
    """Scarico automatico alla somministrazione. Restituisce la quantità non coperta dalla giacenza."""
    from fasas.notifications.services import notify

    lock_audit_chain()
    therapy = administration.therapy
    remaining = Decimal(quantity)
    for lot in candidate_lots(therapy.drug, administration.guest):
        if remaining <= 0:
            break
        take = min(lot.quantity, remaining)
        _move(lot, StockMovement.Kind.ADMINISTRATION, -take, user, administration=administration)
        remaining -= take
    if remaining > 0:
        notify(
            "stock_low",
            f"Giacenza insufficiente: {therapy.drug}",
            f"Somministrazione a {administration.guest} registrata senza giacenza sufficiente "
            f"(mancano {remaining} {therapy.drug.stock_unit}). Verificare il magazzino.",
            link=reverse("pharmacy:stock"),
            guest=administration.guest,
            level="warning",
            dedup_key=f"stock-missing-{therapy.drug_id}-{timezone.localdate()}",
        )
    check_drug_threshold(therapy.drug)
    return remaining


@transaction.atomic
def reverse_administration(administration, user):
    """Storno delle quantità scaricate quando una somministrazione viene annullata."""
    lock_audit_chain()
    for movement in administration.stock_movements.filter(kind=StockMovement.Kind.ADMINISTRATION):
        lot = StockLot.objects.select_for_update().get(pk=movement.lot_id)
        _move(lot, StockMovement.Kind.REVERSAL, -movement.quantity, user, administration=administration,
              notes="Storno per annullamento somministrazione")


def drug_stock_summary():
    today = timezone.localdate()
    config = SystemConfig.get()
    soon = today + datetime.timedelta(days=config.stock_expiry_warning_days)
    rows = []
    for drug in Drug.objects.filter(active=True).prefetch_related("lots"):
        lots = [lot for lot in drug.lots.all() if lot.quantity > 0]
        total = sum((lot.quantity for lot in lots if lot.expiry_date >= today), Decimal("0"))
        rows.append({
            "drug": drug,
            "total": total,
            "low": total < drug.min_stock,
            "expired": [lot for lot in lots if lot.expiry_date < today],
            "expiring": [lot for lot in lots if today <= lot.expiry_date <= soon],
            "lots": lots,
        })
    return rows


def check_drug_threshold(drug):
    from fasas.notifications.services import notify

    today = timezone.localdate()
    total = drug.lots.filter(quantity__gt=0, expiry_date__gte=today).aggregate(t=Sum("quantity"))["t"] or Decimal("0")
    if drug.min_stock and total < drug.min_stock:
        notify(
            "stock_low",
            f"Farmaco in esaurimento: {drug}",
            f"Giacenza {total} {drug.stock_unit}, soglia minima {drug.min_stock}.",
            link=reverse("pharmacy:stock"),
            level="warning",
            dedup_key=f"stock-low-{drug.pk}-{today}",
        )


def stock_alerts():
    """Job periodico: farmaci sotto soglia, in scadenza e scaduti."""
    from fasas.notifications.services import notify

    today = timezone.localdate()
    summary = drug_stock_summary()
    counts = {"low": 0, "expiring": 0, "expired": 0}
    for row in summary:
        drug = row["drug"]
        if row["low"] and drug.min_stock:
            counts["low"] += 1
            check_drug_threshold(drug)
        for lot in row["expiring"]:
            counts["expiring"] += 1
            notify(
                "stock_expiring", f"Farmaco in scadenza: {drug}",
                f"Lotto {lot.lot_number} scade il {lot.expiry_date:%d/%m/%Y} (giacenza {lot.quantity}).",
                link=reverse("pharmacy:stock"), level="info", dedup_key=f"stock-expiring-{lot.pk}",
            )
        for lot in row["expired"]:
            counts["expired"] += 1
            notify(
                "stock_expiring", f"Farmaco SCADUTO: {drug}",
                f"Lotto {lot.lot_number} scaduto il {lot.expiry_date:%d/%m/%Y}: rimuovere e smaltire.",
                link=reverse("pharmacy:stock"), level="warning", dedup_key=f"stock-expired-{lot.pk}-{today}",
            )
    return counts
