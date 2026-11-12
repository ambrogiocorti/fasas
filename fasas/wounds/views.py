from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from fasas.core.views_mixins import VoidRecordView
from fasas.guests.models import Guest
from fasas.guests.services import guests_in_care

from . import services
from .forms import CloseWoundForm, DressingForm, DressingPlanForm, WoundCheckForm, WoundForm
from .models import Dressing, Wound, WoundCheck


def _form_page(request, form, wound_or_guest, title, submit, intro="", multipart=False):
    guest = getattr(wound_or_guest, "guest", wound_or_guest)
    cancel = wound_or_guest.get_absolute_url() if isinstance(wound_or_guest, Wound) else \
        reverse("wounds:guest", args=[guest.pk])
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": title, "submit_label": submit, "cancel_url": cancel,
        "intro": intro, "multipart": multipart,
    })


@permission_required("wounds.view_wound", raise_exception=True)
def guest_wounds(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    wounds = list(Wound.all_objects.filter(guest=guest).select_related("created_by", "closed_by")
                  .order_by("status", "-occurred_at"))
    due = {}
    for row in services.due_list(guests=[guest]):
        due.setdefault(row["wound"].pk, []).append(row)
    open_wounds = [w for w in wounds if w.is_open and not w.is_voided]
    for wound in open_wounds:
        wound.due_rows = due.get(wound.pk, [])
    return render(request, "wounds/guest.html", {
        "guest": guest, "active_tab": "wounds", "open_wounds": open_wounds,
        "other_wounds": [w for w in wounds if w not in open_wounds],
    })


@permission_required("wounds.add_wound", raise_exception=True)
def wound_create(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    form = WoundForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            wound = services.create_wound(guest, request.user, occurred_at=form.cleaned_data["occurred_at"],
                                          **form.wound_data())
            check = form.check_data()
            if check is not None or form.cleaned_data.get("photo"):
                services.add_check(wound, request.user, occurred_at=form.cleaned_data["occurred_at"],
                                   photo=form.cleaned_data.get("photo"), **(check or {"stage": wound.stage}))
        except services.WoundError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Lesione registrata: il coordinatore riceve un avviso.")
            return redirect(wound.get_absolute_url())
    return _form_page(request, form, guest, f"Nuova lesione – {guest}", "Registra lesione",
                      "Sede, tipo e, per le lesioni da pressione, la categoria. Misure e foto si possono aggiungere "
                      "subito o con la prima rilevazione.", multipart=True)


@permission_required("wounds.view_wound", raise_exception=True)
def wound_detail(request, pk):
    wound = get_object_or_404(Wound.all_objects.select_related("guest", "created_by", "closed_by"), pk=pk)
    return render(request, "wounds/detail.html", {
        "wound": wound, "guest": wound.guest, "active_tab": "wounds",
        "checks": WoundCheck.all_objects.filter(wound=wound).select_related("created_by", "photo")
        .order_by("-occurred_at"),
        "plans": wound.plans.select_related("created_by"),
        "dressings": Dressing.all_objects.filter(wound=wound).select_related("created_by", "plan")
        .order_by("-occurred_at")[:200],
        "active_plan": wound.active_plan,
        "due_rows": [r for r in services.due_list(guests=[wound.guest]) if r["wound"].pk == wound.pk]
        if wound.is_open and not wound.is_voided else [],
    })


def _open_wound(pk):
    """Solo lesioni aperte e non annullate: le altre restano consultabili ma non si modificano."""
    return get_object_or_404(Wound.objects.filter(status=Wound.Status.OPEN).select_related("guest"), pk=pk)


@permission_required("wounds.add_woundcheck", raise_exception=True)
def check_create(request, pk):
    wound = _open_wound(pk)
    form = WoundCheckForm(request.POST or None, request.FILES or None, wound=wound)
    if request.method == "POST" and form.is_valid():
        try:
            services.add_check(wound, request.user, occurred_at=form.cleaned_data["occurred_at"],
                               photo=form.cleaned_data.get("photo"), **form.check_data())
        except services.WoundError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Rilevazione registrata.")
            return redirect(wound.get_absolute_url())
    return _form_page(request, form, wound, f"Rilevazione – {wound}", "Registra rilevazione", multipart=True)


@permission_required("wounds.add_dressingplan", raise_exception=True)
def plan_create(request, pk):
    wound = _open_wound(pk)
    current = wound.active_plan
    initial = {"products": current.products, "procedure": current.procedure,
               "interval_days": current.interval_days, "indicated_by": current.indicated_by} if current else None
    form = DressingPlanForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.set_plan(wound, request.user, **form.cleaned_data)
        except services.WoundError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Piano di medicazione salvato" + (": il precedente è terminato oggi."
                                                                         if current else "."))
            return redirect(wound.get_absolute_url())
    return _form_page(request, form, wound, f"Piano di medicazione – {wound}", "Salva piano",
                      "Come indicato dall'infermiere o dal medico. Un nuovo piano sostituisce quello in corso, "
                      "che resta nello storico.")


@permission_required("wounds.add_dressing", raise_exception=True)
def dressing_create(request, pk):
    wound = _open_wound(pk)
    form = DressingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.register_dressing(wound, request.user, **form.cleaned_data)
        except services.WoundError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Medicazione registrata.")
            return redirect(wound.get_absolute_url())
    plan = wound.active_plan
    return _form_page(request, form, wound, f"Medicazione – {wound}", "Registra medicazione",
                      f"Piano in corso: {plan.products} (ogni {plan.interval_days} giorni)." if plan else
                      "Nessun piano di medicazione in corso.")


@require_POST
@permission_required("wounds.add_dressing", raise_exception=True)
def dressing_quick(request, pk):
    """«Fatta adesso» dall'elenco delle medicazioni da fare."""
    wound = _open_wound(pk)
    try:
        services.register_dressing(wound, request.user)
    except services.WoundError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Medicazione registrata: {wound.guest} – {wound}.")
    return redirect("wounds:due")


@permission_required("wounds.change_wound", raise_exception=True)
def wound_close(request, pk):
    wound = _open_wound(pk)
    form = CloseWoundForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.close_wound(wound, request.user, form.cleaned_data["status"], form.cleaned_data["note"],
                                 form.cleaned_data["closed_at"])
        except services.WoundError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Lesione chiusa; il piano di medicazione è terminato.")
            return redirect(wound.get_absolute_url())
    return _form_page(request, form, wound, f"Chiudi lesione – {wound}", "Chiudi lesione")


@permission_required("wounds.view_wound", raise_exception=True)
def due_overview(request):
    rows = services.due_list(guests=guests_in_care())
    return render(request, "wounds/due.html", {"rows": rows})


class WoundVoidView(VoidRecordView):
    model = Wound


class WoundCheckVoidView(VoidRecordView):
    model = WoundCheck


class DressingVoidView(VoidRecordView):
    model = Dressing
