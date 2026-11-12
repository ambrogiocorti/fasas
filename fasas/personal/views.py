import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from fasas.guests.models import Guest

from . import services
from .forms import ItemForm, MovementForm, PeriodForm, VoidForm
from .models import CashMovement, PersonalItem


def _page(request, form, guest, title, submit, multipart=False, intro=""):
    return render(request, "personal/form.html", {
        "form": form, "guest": guest, "page_title": title, "submit_label": submit, "multipart": multipart,
        "intro": intro, "cancel_url": reverse("personal:guest", args=[guest.pk])})


@permission_required("personal.view_cashmovement", raise_exception=True)
def overview(request):
    """Saldi di tutti gli ospiti presenti: vista per l'ufficio amministrativo e il coordinatore."""
    guests = Guest.objects.exclude(status=Guest.Status.ARCHIVED).order_by("last_name", "first_name")
    totals = services.balances(guests)
    rows = [{"guest": g, "balance": totals.get(g.pk, 0),
             "items": g.personal_items.filter(status="present").count()} for g in guests]
    return render(request, "personal/overview.html", {"rows": rows, "total": sum(r["balance"] for r in rows)})


@permission_required("personal.view_cashmovement", raise_exception=True)
def guest_view(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    today = timezone.localdate()
    return render(request, "personal/guest.html", {
        "guest": guest, "active_tab": "personal",
        "balance": services.balance(guest),
        "movements": CashMovement.objects.filter(guest=guest).select_related("created_by", "voided_by")[:200],
        "items": guest.personal_items.all(),
        "period_start": today.replace(day=1), "period_end": today,
    })


@permission_required("personal.add_cashmovement", raise_exception=True)
def movement_create(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    form = MovementForm(request.POST or None, request.FILES or None,
                        initial={"occurred_on": timezone.localdate(), "kind": request.GET.get("tipo", "expense")})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            movement = services.add_movement(guest, request.user, data["kind"], data["amount"], data["description"],
                                             data["occurred_on"], data["counterpart"], data.get("receipt"))
        except services.CashError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"{movement.get_kind_display()} di {movement.amount:.2f} € registrata. "
                                      f"Saldo: {services.balance(guest):.2f} €.")
            return redirect("personal:guest", guest_pk=guest.pk)
    return _page(request, form, guest, "Nuovo movimento di cassa", "Registra", multipart=True,
                 intro=f"Saldo attuale: {services.balance(guest):.2f} €. Le uscite non possono superare il saldo.")


@permission_required("personal.void_cashmovement", raise_exception=True)
def movement_void(request, pk):
    movement = get_object_or_404(CashMovement.objects.select_related("guest"), pk=pk)
    form = VoidForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.void_movement(movement, request.user, form.cleaned_data["reason"])
        except services.CashError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Movimento annullato: resta visibile nell'elenco e nell'audit.")
            return redirect("personal:guest", guest_pk=movement.guest_id)
    return _page(request, form, movement.guest, f"Annulla: {movement}", "Annulla il movimento")


@permission_required("personal.view_cashmovement", raise_exception=True)
def receipt(request, pk):
    movement = get_object_or_404(CashMovement.objects.select_related("guest"), pk=pk, receipt_storage__gt="")
    try:
        data = services.read_receipt(movement, request.user)
    except services.CashError as exc:
        messages.error(request, str(exc))
        return redirect("personal:guest", guest_pk=movement.guest_id)
    extension = "pdf" if movement.receipt_type == "application/pdf" else "jpg"
    response = HttpResponse(data, content_type=movement.receipt_type)
    response["Content-Disposition"] = f'inline; filename="scontrino-{movement.pk}.{extension}"'
    response["Cache-Control"] = "no-store"
    return response


@permission_required("personal.view_cashmovement", raise_exception=True)
def statement(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    today = timezone.localdate()
    form = PeriodForm(request.GET or None, initial={"start": today.replace(day=1), "end": today})
    if request.GET and form.is_valid():
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        pdf = services.statement_pdf(guest, start, end, request.user)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (f'attachment; filename="rendiconto-cassa-{guest.pk}-'
                                           f'{start:%Y%m%d}-{end:%Y%m%d}.pdf"')
        return response
    if not request.GET:
        start = today.replace(day=1) - datetime.timedelta(days=1)
        form = PeriodForm(initial={"start": start.replace(day=1), "end": start})
    return render(request, "personal/statement.html", {"form": form, "guest": guest})


@permission_required("personal.add_personalitem", raise_exception=True)
def item_create(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    form = ItemForm(request.POST or None, initial={"received_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        if guest.is_archived:
            form.add_error(None, "La cartella dell'ospite è archiviata.")
        else:
            item = form.save(commit=False)
            item.guest, item.created_by = guest, request.user
            item.save()
            messages.success(request, f"Oggetto registrato: {item.name}.")
            return redirect("personal:guest", guest_pk=guest.pk)
    return _page(request, form, guest, "Nuovo oggetto personale", "Registra")


@permission_required("personal.change_personalitem", raise_exception=True)
def item_update(request, pk):
    item = get_object_or_404(PersonalItem.objects.select_related("guest"), pk=pk)
    form = ItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.updated_by = request.user
        if item.status != PersonalItem.Status.PRESENT and not item.status_date:
            item.status_date = timezone.localdate()
        item.save()
        messages.success(request, "Oggetto aggiornato.")
        return redirect("personal:guest", guest_pk=item.guest_id)
    return _page(request, form, item.guest, f"Modifica: {item.name}", "Salva")
