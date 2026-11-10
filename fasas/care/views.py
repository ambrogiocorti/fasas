import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from fasas.core.shifts import resolve_shift, shift_label
from fasas.core.views_mixins import VoidRecordView
from fasas.guests.models import Guest
from fasas.guests.services import guests_in_care

from . import services
from .forms import CareTaskForm, CheckForm, EndTaskForm
from .models import CareTask, CareTaskCheck


def _form_page(request, form, guest, title, submit, cancel, intro=""):
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": title, "submit_label": submit, "cancel_url": cancel,
        "intro": intro,
    })


def _slot_from_post(request):
    task = get_object_or_404(CareTask.objects.select_related("guest"), pk=request.POST.get("task") or
                             request.GET.get("task"))
    raw_day = request.POST.get("day") or request.GET.get("day") or ""
    raw_time = request.POST.get("time") or request.GET.get("time") or ""
    try:
        day = datetime.date.fromisoformat(raw_day)
        time = datetime.datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        return task, None, None
    return task, day, time


def _back(request):
    target = request.POST.get("next") or ""
    return redirect(target if target in (reverse("care:due"),) or target.startswith("/attivita/ospite/")
                    else reverse("care:due"))


@permission_required("care.view_caretaskcheck", raise_exception=True)
def due(request):
    """Attività del turno in corso, in ordine di orario, con le spunte e i ritardi."""
    day, shift = resolve_shift()
    now = timezone.now()
    guests = guests_in_care().filter(status=Guest.Status.ACTIVE)
    slots = services.shift_slots(day, shift, guests)
    current = {s.key for s in slots}
    late_before = [s for s in services.late_slots(now, guests) if s.key not in current]
    return render(request, "care/due.html", {
        "slots": slots, "late_before": late_before, "now": now, "day": day, "shift_name": shift_label(shift),
        "done": sum(1 for s in slots if s.done), "late": [s for s in slots if s.late(now)],
    })


@require_POST
@permission_required("care.add_caretaskcheck", raise_exception=True)
def check_quick(request):
    task, day, time = _slot_from_post(request)
    if day is None:
        messages.error(request, "Orario non valido.")
        return _back(request)
    try:
        services.register_check(task, request.user, day, time)
    except services.CareError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, f"{task.name} delle {time:%H:%M} registrata: {task.guest}.")
    return _back(request)


@permission_required("care.add_caretaskcheck", raise_exception=True)
def check_form(request):
    task, day, time = _slot_from_post(request)
    if day is None:
        messages.error(request, "Orario non valido.")
        return redirect("care:due")
    form = CheckForm(request.POST or None, initial={"status": "not_done"})
    if request.method == "POST" and form.is_valid():
        try:
            services.register_check(task, request.user, day, time, form.cleaned_data["status"],
                                    form.cleaned_data["notes"])
        except services.CareError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, f"{task.name} delle {time:%H:%M} registrata: {task.guest}.")
            return redirect("care:due")
    return _form_page(request, form, task.guest, f"{task.name} delle {time:%H:%M} del {day:%d/%m}", "Registra",
                      reverse("care:due"), intro=task.instructions)


@permission_required("care.view_caretask", raise_exception=True)
def guest_tasks(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    since = timezone.now() - datetime.timedelta(days=3)
    return render(request, "care/guest.html", {
        "guest": guest, "active_tab": "care",
        "tasks": guest.care_tasks.filter(active=True),
        "ended": guest.care_tasks.filter(active=False)[:20],
        "checks": CareTaskCheck.all_objects.filter(guest=guest, occurred_at__gte=since)
        .select_related("task", "created_by").order_by("-occurred_at")[:100],
    })


@permission_required("care.add_caretask", raise_exception=True)
def task_create(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    if guest.is_archived:
        messages.error(request, "Cartella archiviata: non si aggiungono attività.")
        return redirect("care:guest", guest_pk=guest.pk)
    form = CareTaskForm(request.POST or None, initial={"kind": request.GET.get("tipo")})
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.guest, task.created_by = guest, request.user
        task.save()
        messages.success(request, f"Attività aggiunta: {task.name} ({task.schedule_display()}).")
        return redirect("care:guest", guest_pk=guest.pk)
    return _form_page(request, form, guest, "Nuova attività a orario", "Aggiungi",
                      reverse("care:guest", args=[guest.pk]),
                      intro="Cosa fare e quando, come deciso dall'équipe (es. dal PAI o dal piano di medicazione).")


@permission_required("care.change_caretask", raise_exception=True)
def task_update(request, pk):
    task = get_object_or_404(CareTask.objects.select_related("guest"), pk=pk, active=True)
    form = CareTaskForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.updated_by = request.user
        task.save()
        messages.success(request, "Attività aggiornata: valgono i nuovi orari.")
        return redirect("care:guest", guest_pk=task.guest_id)
    return _form_page(request, form, task.guest, f"Modifica: {task.name}", "Salva",
                      reverse("care:guest", args=[task.guest_id]))


@permission_required("care.change_caretask", raise_exception=True)
def task_end(request, pk):
    task = get_object_or_404(CareTask.objects.select_related("guest"), pk=pk, active=True)
    form = EndTaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.end_task(task, request.user, form.cleaned_data["reason"])
        messages.success(request, f"Attività terminata: {task.name}. Le registrazioni restano nello storico.")
        return redirect("care:guest", guest_pk=task.guest_id)
    return _form_page(request, form, task.guest, f"Termina: {task.name}", "Termina l'attività",
                      reverse("care:guest", args=[task.guest_id]))


class CheckVoidView(VoidRecordView):
    model = CareTaskCheck
