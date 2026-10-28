import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from fasas.core.locking import creation_decision
from fasas.core.models import SystemConfig
from fasas.core.shifts import SHIFT_ORDER, Shift, resolve_shift, shift_bounds
from fasas.core.views_mixins import LockedUpdateMixin, PermRequiredMixin, RecordCreateMixin, VoidRecordView
from fasas.guests.models import Guest
from fasas.guests.services import guests_in_care

from . import services
from .forms import (
    CloseShiftForm,
    DailyRecordForm,
    DiaryEntryForm,
    EvacuationForm,
    ReopenShiftForm,
    ShiftAssignmentForm,
    ShiftDailyRecordForm,
)
from .models import ChecklistItem, DailyRecord, DiaryEntry, EvacuationRecord, ShiftAssignment, ShiftClosure


def _day_shift(request):
    day, shift = resolve_shift()
    try:
        if request.GET.get("date"):
            day = datetime.date.fromisoformat(request.GET["date"])
    except ValueError:
        pass
    if request.GET.get("shift") in Shift.values:
        shift = request.GET["shift"]
    return day, shift


def _shift_nav(day, shift):
    return {
        "day": day, "shift": shift, "shift_label": Shift(shift).label, "shifts": Shift.choices,
        "prev_day": day - datetime.timedelta(days=1), "next_day": day + datetime.timedelta(days=1),
        "closed": services.is_shift_closed(day, shift),
    }


# --- Registro giornaliero ---------------------------------------------------------------------

@permission_required("daily.view_dailyrecord", raise_exception=True)
def shift_register(request):
    """Registro del turno per tutti gli ospiti, con inserimento rapido."""
    day, shift = _day_shift(request)
    start, end = shift_bounds(day, shift)
    form = ShiftDailyRecordForm(request.POST or None, initial={
        "occurred_at": min(timezone.localtime(), timezone.localtime(end) - datetime.timedelta(minutes=1)),
        "guest": request.GET.get("guest"),
    })
    if request.method == "POST":
        if not request.user.has_perm("daily.add_dailyrecord"):
            raise PermissionDenied
        if form.is_valid():
            decision = creation_decision(form.cleaned_data["guest"], form.cleaned_data["occurred_at"], request.user)
            if decision.allowed:
                form.save()
                messages.success(request, "Registrazione salvata.")
                return redirect(f"{reverse('daily:register')}?date={day}&shift={shift}")
            form.add_error(None, decision.message)
    records = DailyRecord.objects.filter(shift_date=day, shift=shift).select_related("guest", "created_by")
    diary = DiaryEntry.objects.filter(shift_date=day, shift=shift).select_related("guest", "created_by")
    return render(request, "daily/shift_register.html", {
        **_shift_nav(day, shift), "records": records, "diary": diary, "form": form,
    })


@permission_required("daily.view_dailyrecord", raise_exception=True)
def guest_daily(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    days, last = services.days_since_last_evacuation(guest)
    return render(request, "daily/guest_daily.html", {
        "guest": guest, "active_tab": "daily",
        "records": DailyRecord.all_objects.filter(guest=guest).select_related("created_by")[:200],
        "evacuations": EvacuationRecord.all_objects.filter(guest=guest).select_related("created_by")[:60],
        "days_since_evacuation": days, "last_evacuation": last,
        "evacuation_mode": SystemConfig.get().evacuation_mode,
    })


class DailyRecordCreateView(PermRequiredMixin, RecordCreateMixin, CreateView):
    permission_required = "daily.add_dailyrecord"
    model = DailyRecord
    form_class = DailyRecordForm
    page_title = "Nuova registrazione giornaliera"

    def get_initial(self):
        return {"occurred_at": timezone.localtime(), "category": self.request.GET.get("category"),
                "meal": self.request.GET.get("meal")}

    def get_success_url(self):
        return reverse("daily:guest_daily", args=[self.get_guest().pk])


class DailyRecordUpdateView(PermRequiredMixin, LockedUpdateMixin, UpdateView):
    permission_required = "daily.change_dailyrecord"
    model = DailyRecord
    form_class = DailyRecordForm
    page_title = "Modifica registrazione"

    def get_success_url(self):
        return reverse("daily:guest_daily", args=[self.object.guest_id])


class DailyRecordVoidView(VoidRecordView):
    model = DailyRecord


# --- Evacuazioni ------------------------------------------------------------------------------

@permission_required("daily.view_evacuationrecord", raise_exception=True)
def evacuation_overview(request):
    config = SystemConfig.get()
    today = timezone.localdate()
    from fasas.protocols.models import Protocol

    protocol = Protocol.objects.filter(kind=Protocol.Kind.EVACUATION, active=True).first()
    threshold = int((protocol.params or {}).get("days", 3)) if protocol else 3
    rows = services.evacuation_overview(guests_in_care().filter(status=Guest.Status.ACTIVE), today)
    recorded_today = set(EvacuationRecord.objects.filter(shift_date=today).values_list("guest_id", flat=True))
    for row in rows:
        row["recorded_today"] = row["guest"].pk in recorded_today
        row["alert"] = row["days"] >= threshold
        row["warning"] = row["days"] == threshold - 1
    return render(request, "daily/evacuations.html", {
        "rows": rows, "mode": config.evacuation_mode, "threshold": threshold, "today": today,
    })


@require_POST
@permission_required("daily.add_evacuationrecord", raise_exception=True)
def evacuation_quick(request, guest_pk):
    """Pulsanti rapidi SI/NO dalla panoramica evacuazioni."""
    guest = get_object_or_404(Guest, pk=guest_pk)
    outcome = request.POST.get("outcome") == "1"
    decision = creation_decision(guest, timezone.now(), request.user)
    config = SystemConfig.get()
    if not decision.allowed:
        messages.error(request, decision.message)
    elif not outcome and config.evacuation_mode == SystemConfig.EvacuationMode.ON_EVENT:
        messages.info(request, "In modalità B si registrano solo le evacuazioni avvenute.")
    else:
        EvacuationRecord.objects.create(guest=guest, outcome=outcome, notes=request.POST.get("notes", "")[:255])
        messages.success(request, f"{guest}: evacuazione {'SI' if outcome else 'NO'} registrata.")
    return redirect(request.POST.get("next") or reverse("daily:evacuations"))


class EvacuationCreateView(PermRequiredMixin, RecordCreateMixin, CreateView):
    permission_required = "daily.add_evacuationrecord"
    model = EvacuationRecord
    form_class = EvacuationForm
    page_title = "Registra evacuazione"

    def get_initial(self):
        return {"occurred_at": timezone.localtime(), "outcome": True}

    def form_valid(self, form):
        config = SystemConfig.get()
        if not form.cleaned_data["outcome"] and config.evacuation_mode == SystemConfig.EvacuationMode.ON_EVENT:
            form.add_error("outcome", "In modalità B si registrano solo le evacuazioni avvenute.")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("daily:guest_daily", args=[self.get_guest().pk])


class EvacuationUpdateView(PermRequiredMixin, LockedUpdateMixin, UpdateView):
    permission_required = "daily.change_evacuationrecord"
    model = EvacuationRecord
    form_class = EvacuationForm
    page_title = "Modifica evacuazione"

    def get_success_url(self):
        return reverse("daily:guest_daily", args=[self.object.guest_id])


class EvacuationVoidView(VoidRecordView):
    model = EvacuationRecord


# --- Diario assistenziale ---------------------------------------------------------------------

@permission_required("daily.view_diaryentry", raise_exception=True)
def guest_diary(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    entries = DiaryEntry.all_objects.filter(guest=guest).select_related("created_by")
    if request.GET.get("relevant"):
        entries = entries.filter(is_relevant=True)
    return render(request, "daily/guest_diary.html", {"guest": guest, "entries": entries[:300], "active_tab": "diary"})


class DiaryCreateView(PermRequiredMixin, RecordCreateMixin, CreateView):
    permission_required = "daily.add_diaryentry"
    model = DiaryEntry
    form_class = DiaryEntryForm
    page_title = "Nuova nota di diario"

    def get_initial(self):
        return {"occurred_at": timezone.localtime()}

    def get_success_url(self):
        return reverse("daily:guest_diary", args=[self.get_guest().pk])


class DiaryUpdateView(PermRequiredMixin, LockedUpdateMixin, UpdateView):
    permission_required = "daily.change_diaryentry"
    model = DiaryEntry
    form_class = DiaryEntryForm
    page_title = "Modifica nota di diario"

    def get_success_url(self):
        return reverse("daily:guest_diary", args=[self.object.guest_id])


class DiaryVoidView(VoidRecordView):
    model = DiaryEntry


# --- Checklist --------------------------------------------------------------------------------

@permission_required("daily.view_checklistcheck", raise_exception=True)
def checklist(request):
    day, shift = _day_shift(request)
    status = services.checklist_status(day, shift)
    return render(request, "daily/checklist.html", {**_shift_nav(day, shift), "status": status})


@require_POST
@permission_required("daily.add_checklistcheck", raise_exception=True)
def checklist_toggle(request):
    try:
        day = datetime.date.fromisoformat(request.POST["date"])
        shift = request.POST["shift"]
        item = get_object_or_404(ChecklistItem, pk=request.POST["item"])
    except (KeyError, ValueError):
        messages.error(request, "Richiesta non valida.")
        return redirect("daily:checklist")
    guest = get_object_or_404(Guest, pk=request.POST["guest"]) if request.POST.get("guest") else None
    action = request.POST.get("action", "done")
    try:
        if action == "undo":
            services.unmark_check(day, shift, item, guest)
        else:
            services.mark_check(day, shift, item, request.user, guest, not_applicable=action == "na",
                                notes=request.POST.get("notes", "")[:255])
    except services.ShiftClosedError as exc:
        messages.error(request, str(exc))
    return redirect(f"{reverse('daily:checklist')}?date={day}&shift={shift}#item-{item.pk}")


# --- Turni e blocco giornata ------------------------------------------------------------------

@permission_required("daily.view_shiftassignment", raise_exception=True)
def shift_roster(request):
    try:
        day = datetime.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = timezone.localdate()
    week = [day + datetime.timedelta(days=i) for i in range(-3, 4)]
    assignments = ShiftAssignment.objects.filter(date__in=week).select_related("user")
    grid = []
    for d in week:
        row = {"day": d, "shifts": []}
        for s in SHIFT_ORDER:
            row["shifts"].append({"shift": s, "label": Shift(s).label,
                                  "people": [a for a in assignments if a.date == d and a.shift == s]})
        grid.append(row)
    form = ShiftAssignmentForm(request.POST or None, initial={"date": day})
    if request.method == "POST":
        if not request.user.has_perm("daily.add_shiftassignment"):
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, "Turno assegnato.")
            return redirect(f"{reverse('daily:roster')}?date={day}")
    return render(request, "daily/roster.html", {
        "grid": grid, "form": form, "day": day,
        "prev": day - datetime.timedelta(days=7), "next": day + datetime.timedelta(days=7),
    })


@require_POST
def check_in(request):
    """«Prendo servizio»: l'operatore si registra nel turno corrente."""
    day, shift = resolve_shift()
    assignment, _ = ShiftAssignment.objects.get_or_create(date=day, shift=shift, user=request.user)
    if not assignment.checked_in_at:
        assignment.checked_in_at = timezone.now()
        assignment.save()
    messages.success(request, f"Presa servizio registrata: turno {Shift(shift).label} del {day:%d/%m/%Y}.")
    return redirect("core:dashboard")


@permission_required("daily.view_shiftclosure", raise_exception=True)
def closures(request):
    day, shift = resolve_shift()
    days = [timezone.localdate() - datetime.timedelta(days=i) for i in range(0, 8)]
    existing = {(c.date, c.shift): c for c in ShiftClosure.objects.filter(date__in=days)}
    rows = []
    for d in days:
        rows.append({"day": d, "shifts": [
            {"shift": s, "label": Shift(s).label, "closure": existing.get((d, s)),
             "is_current": (d, s) == (day, shift), "future": shift_bounds(d, s)[0] > timezone.now()}
            for s in SHIFT_ORDER
        ]})
    return render(request, "daily/closures.html", {"rows": rows, "config": SystemConfig.get()})


@permission_required("daily.close_shift", raise_exception=True)
def close_shift_view(request):
    day, shift = _day_shift(request)
    if shift_bounds(day, shift)[0] > timezone.now():
        messages.error(request, "Non si può chiudere un turno non ancora iniziato.")
        return redirect("daily:closures")
    status = services.checklist_status(day, shift)
    form = CloseShiftForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        closure = services.close_shift(day, shift, request.user, handover_notes=form.cleaned_data["handover_notes"])
        messages.success(request, f"Turno {Shift(shift).label} del {day:%d/%m/%Y} chiuso.")
        return redirect("daily:closure_detail", pk=closure.pk)
    return render(request, "daily/close_shift.html", {**_shift_nav(day, shift), "status": status, "form": form})


@permission_required("daily.view_shiftclosure", raise_exception=True)
def closure_detail(request, pk):
    closure = get_object_or_404(ShiftClosure, pk=pk)
    form = ReopenShiftForm(request.POST or None)
    config = SystemConfig.get()
    if request.method == "POST" and form.is_valid():
        try:
            services.reopen_shift(closure, request.user, form.cleaned_data["reason"])
            messages.warning(request, "Turno riaperto in via straordinaria. Ricordare di richiuderlo.")
        except services.ShiftClosedError as exc:
            messages.error(request, str(exc))
        return redirect("daily:closure_detail", pk=closure.pk)
    return render(request, "daily/closure_detail.html", {
        "closure": closure, "form": form,
        "can_reopen": config.allow_admin_reopen and request.user.has_perm("daily.reopen_shift") and closure.is_closed,
    })
