from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import LotAdjustForm, LotLoadForm
from .models import DrugInteraction, StockLot
from .services import adjust_lot, drug_stock_summary, load_lot


@permission_required("pharmacy.view_stocklot", raise_exception=True)
def stock(request):
    rows = drug_stock_summary()
    status = request.GET.get("status")
    if status == "low":
        rows = [r for r in rows if r["low"]]
    elif status == "expiring":
        rows = [r for r in rows if r["expiring"] or r["expired"]]
    q = request.GET.get("q", "").strip().lower()
    if q:
        rows = [r for r in rows if q in r["drug"].name.lower() or q in r["drug"].active_ingredient.lower()]
    return render(request, "pharmacy/stock.html", {"rows": rows, "status": status, "q": q})


@permission_required("pharmacy.add_stocklot", raise_exception=True)
def lot_load(request):
    form = LotLoadForm(request.POST or None, initial={"drug": request.GET.get("drug")})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        load_lot(data["drug"], data["lot_number"], data["expiry_date"], data["quantity"], request.user,
                 guest=data["guest"], supplier=data["supplier"], notes=data["notes"])
        messages.success(request, "Carico registrato.")
        return redirect("pharmacy:stock")
    return render(request, "generic/form.html", {"form": form, "page_title": "Carico farmaco",
                                                 "cancel_url": reverse("pharmacy:stock")})


@permission_required("pharmacy.view_stocklot", raise_exception=True)
def lot_detail(request, pk):
    lot = get_object_or_404(StockLot.objects.select_related("drug", "guest"), pk=pk)
    form = LotAdjustForm(request.POST or None, initial={"new_quantity": lot.quantity})
    if request.method == "POST":
        if not request.user.has_perm("pharmacy.change_stocklot"):
            messages.error(request, "Non hai il permesso di rettificare le giacenze.")
        elif form.is_valid():
            adjust_lot(lot, form.cleaned_data["new_quantity"], request.user, form.cleaned_data["kind"],
                       form.cleaned_data["notes"])
            messages.success(request, "Movimento registrato.")
            return redirect("pharmacy:lot_detail", pk=lot.pk)
    movements = lot.movements.select_related("created_by", "administration__guest")[:300]
    return render(request, "pharmacy/lot_detail.html", {"lot": lot, "movements": movements, "form": form})


@require_POST
@permission_required("pharmacy.validate_druginteraction", raise_exception=True)
def interaction_validate(request, pk):
    """Il medico della struttura conferma l'interazione: solo da allora entra nei promemoria sulle terapie."""
    interaction = get_object_or_404(DrugInteraction, pk=pk)
    interaction.validated_by, interaction.validated_at = request.user, timezone.now()
    interaction.save(update_fields=["validated_by", "validated_at"])
    messages.success(request, f"Interazione {interaction} validata.")
    return redirect("pharmacy:interaction_list")
