import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, UpdateView

from fasas.audit.context import audit_context
from fasas.core.locking import creation_decision, edit_decision
from fasas.core.shifts import Shift, resolve_shift, shift_bounds
from fasas.core.views_mixins import (
    FormPageMixin,
    GuestMixin,
    LockedUpdateMixin,
    PermRequiredMixin,
    RecordCreateMixin,
    VoidForm,
    VoidRecordView,
)
from fasas.guests.models import Guest
from fasas.guests.services import guests_in_care

from . import services
from .forms import (
    ClinicalEventForm,
    EmergencyForm,
    ParameterReadingForm,
    QuickParametersForm,
    RestraintForm,
    SOSAdministrationForm,
    SOSValidationForm,
    TherapyForm,
    TherapyStatusForm,
)
from .models import ClinicalEvent, ParameterReading, ParameterType, Restraint, Therapy, TherapyAdministration


def _guest(pk):
    return get_object_or_404(Guest, pk=pk)


def _parse_shift(request):
    day, shift = resolve_shift()
    try:
        if request.GET.get("date"):
            day = datetime.date.fromisoformat(request.GET["date"])
    except ValueError:
        pass
    if request.GET.get("shift") in Shift.values:
        shift = request.GET["shift"]
    return day, shift


# --- Terapie ----------------------------------------------------------------------------------

@permission_required("clinical.view_therapy", raise_exception=True)
def guest_therapies(request, guest_pk):
    guest = _guest(guest_pk)
    therapies = guest.therapies.select_related("drug", "prescriber")
    return render(request, "clinical/guest_therapies.html", {
        "guest": guest, "active_tab": "therapies",
        "scheduled": therapies.filter(status=Therapy.Status.ACTIVE, is_sos=False),
        "sos": therapies.filter(status=Therapy.Status.ACTIVE, is_sos=True),
        "inactive": therapies.exclude(status=Therapy.Status.ACTIVE).order_by("-updated_at"),
    })


class TherapyCreateView(PermRequiredMixin, GuestMixin, FormPageMixin, CreateView):
    permission_required = "clinical.add_therapy"
    model = Therapy
    form_class = TherapyForm
    template_name = "clinical/therapy_form.html"
    page_title = "Nuova terapia"

    def dispatch(self, request, *args, **kwargs):
        if self.get_guest().is_archived:
            messages.error(request, "Cartella archiviata.")
            return redirect(self.get_guest().get_absolute_url())
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.is_doctor:
            initial["prescriber"] = self.request.user
        initial["is_sos"] = self.request.GET.get("sos") == "1"
        return initial

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "guest": self.get_guest()}

    def form_valid(self, form):
        form.instance.guest = self.get_guest()
        form.instance.conflict_acknowledged = "\n".join(w.message for w in form.warnings)
        response = super().form_valid(form)
        services.notify_conflicts(self.object, form.warnings, self.request.user)
        messages.success(self.request, "Terapia registrata.")
        return response

    def get_success_url(self):
        return reverse("clinical:guest_therapies", args=[self.get_guest().pk])


class TherapyUpdateView(PermRequiredMixin, FormPageMixin, UpdateView):
    permission_required = "clinical.change_therapy"
    model = Therapy
    form_class = TherapyForm
    template_name = "clinical/therapy_form.html"

    def dispatch(self, request, *args, **kwargs):
        therapy = self.get_object()
        if therapy.guest.is_archived or therapy.status == Therapy.Status.ENDED:
            messages.error(request, "Una terapia terminata o di un ospite archiviato non è modificabile.")
            return redirect(therapy.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)

    def get_page_title(self):
        return f"Modifica terapia: {self.object}"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "guest": self.object.guest}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "guest": self.object.guest}

    def form_valid(self, form):
        if form.warnings:
            form.instance.conflict_acknowledged = "\n".join(w.message for w in form.warnings)
        response = super().form_valid(form)
        services.notify_conflicts(self.object, form.warnings, self.request.user)
        messages.success(self.request, "Terapia aggiornata (modifica registrata nello storico).")
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()


class TherapyDetailView(PermRequiredMixin, DetailView):
    permission_required = "clinical.view_therapy"
    model = Therapy
    template_name = "clinical/therapy_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["guest"] = self.object.guest
        context["active_tab"] = "therapies"
        context["administrations"] = TherapyAdministration.all_objects.filter(therapy=self.object).select_related(
            "created_by", "validated_by"
        )[:200]
        context["status_form"] = TherapyStatusForm(initial={"status": self.object.status})
        return context


@require_POST
@permission_required("clinical.change_therapy", raise_exception=True)
def therapy_status(request, pk):
    therapy = get_object_or_404(Therapy, pk=pk)
    if therapy.guest.is_archived:
        raise PermissionDenied("Cartella archiviata.")
    form = TherapyStatusForm(request.POST)
    if form.is_valid():
        with audit_context(reason=form.cleaned_data["reason"]):
            therapy.status = form.cleaned_data["status"]
            therapy.status_reason = form.cleaned_data["reason"]
            if therapy.status == Therapy.Status.ENDED and not therapy.end_date:
                therapy.end_date = timezone.localdate()
            therapy.save()
        messages.success(request, f"Terapia ora «{therapy.get_status_display()}».")
    return redirect(therapy.get_absolute_url())


@permission_required("clinical.add_therapy", raise_exception=True)
def therapy_overview(request):
    """Terapie in corso di tutti gli ospiti: il quadro del prescrittore (medico o coordinatore)."""
    today = timezone.localdate()
    soon = today + datetime.timedelta(days=7)
    guests = guests_in_care().prefetch_related("allergies")
    q = request.GET.get("q", "").strip()
    if q:
        guests = guests.filter(last_name__icontains=q) | guests.filter(first_name__icontains=q)
    therapies = Therapy.objects.filter(guest__in=guests).exclude(status=Therapy.Status.ENDED).select_related(
        "drug", "prescriber").order_by("is_sos", "drug__name")
    by_guest = {}
    for therapy in therapies:
        by_guest.setdefault(therapy.guest_id, []).append(therapy)
    rows = [{
        "guest": guest, "therapies": by_guest.get(guest.pk, []),
        "ending": [t for t in by_guest.get(guest.pk, []) if t.end_date and today <= t.end_date <= soon],
    } for guest in guests.order_by("last_name", "first_name")]
    return render(request, "clinical/therapy_overview.html", {"rows": rows, "q": q, "today": today})


# --- Giro farmaci e somministrazioni ----------------------------------------------------------

@permission_required("clinical.add_therapyadministration", raise_exception=True)
def administration_board(request):
    day, shift = _parse_shift(request)
    guests = guests_in_care()
    if request.GET.get("guest"):
        guests = guests.filter(pk=request.GET["guest"])
    doses = services.scheduled_doses(day, shift, guests)
    grouped = {}
    for dose in doses:
        grouped.setdefault(dose.guest, []).append(dose)
    start, end = shift_bounds(day, shift)
    sos_today = TherapyAdministration.objects.filter(is_sos=True, occurred_at__gte=start, occurred_at__lt=end).select_related(
        "therapy__drug", "guest"
    )
    from fasas.daily.services import is_shift_closed

    return render(request, "clinical/administration_board.html", {
        "day": day, "shift": shift, "shift_label": Shift(shift).label, "grouped": grouped,
        "total": len(doses), "done": sum(1 for d in doses if d.done), "sos_today": sos_today,
        "shifts": Shift.choices, "closed": is_shift_closed(day, shift),
        "prev_day": day - datetime.timedelta(days=1), "next_day": day + datetime.timedelta(days=1),
    })


@require_POST
@permission_required("clinical.add_therapyadministration", raise_exception=True)
def administer(request, therapy_pk):
    therapy = get_object_or_404(Therapy.objects.select_related("guest", "drug"), pk=therapy_pk)
    try:
        day = datetime.date.fromisoformat(request.POST["day"])
        t = datetime.datetime.strptime(request.POST["time"], "%H:%M").time()
    except (KeyError, ValueError):
        messages.error(request, "Dose programmata non valida.")
        return redirect("clinical:board")
    status = request.POST.get("status", TherapyAdministration.Status.GIVEN)
    if status not in TherapyAdministration.Status.values:
        status = TherapyAdministration.Status.GIVEN
    decision = creation_decision(therapy.guest, timezone.now(), request.user)
    if not decision.allowed:
        messages.error(request, decision.message)
    elif TherapyAdministration.objects.filter(therapy=therapy, scheduled_date=day, scheduled_time=t).exists():
        messages.warning(request, "Questa dose risulta già registrata.")
    else:
        services.register_administration(
            therapy, request.user, status=status, scheduled_date=day, scheduled_time=t,
            notes=request.POST.get("notes", "")[:500],
        )
        messages.success(request, f"{therapy.drug} – {therapy.guest}: {TherapyAdministration.Status(status).label}.")
    return redirect(request.POST.get("next") or reverse("clinical:board"))


@permission_required("clinical.add_therapyadministration", raise_exception=True)
def sos_administer(request, guest_pk):
    guest = _guest(guest_pk)
    form = SOSAdministrationForm(request.POST or None, guest=guest,
                                 initial={"therapy": request.GET.get("therapy"), "occurred_at": timezone.localtime()})
    if request.method == "POST" and form.is_valid():
        occurred_at = form.cleaned_data["occurred_at"]
        decision = creation_decision(guest, occurred_at, request.user)
        if not decision.allowed:
            form.add_error(None, decision.message)
        else:
            adm = services.register_administration(
                form.cleaned_data["therapy"], request.user, occurred_at=occurred_at,
                notes=form.cleaned_data["notes"], dose_given=form.cleaned_data["dose_given"],
                sos_reason=form.cleaned_data["sos_reason"],
            )
            if adm.validation_status == TherapyAdministration.Validation.PENDING:
                messages.warning(request, "Somministrazione SOS registrata: in attesa di validazione.")
            else:
                messages.success(request, "Somministrazione SOS registrata.")
            return redirect(guest.get_absolute_url())
    return render(request, "clinical/sos_form.html", {
        "form": form, "guest": guest, "page_title": "Somministrazione farmaco SOS",
        "cancel_url": guest.get_absolute_url(),
    })


@permission_required("clinical.validate_sos", raise_exception=True)
def sos_pending(request):
    pending = TherapyAdministration.objects.filter(
        is_sos=True, validation_status=TherapyAdministration.Validation.PENDING
    ).select_related("therapy__drug", "guest", "created_by")
    return render(request, "clinical/sos_pending.html", {"pending": pending, "form": SOSValidationForm()})


@require_POST
@permission_required("clinical.validate_sos", raise_exception=True)
def sos_validate(request, pk):
    adm = get_object_or_404(TherapyAdministration, pk=pk, is_sos=True)
    form = SOSValidationForm(request.POST)
    if form.is_valid():
        services.validate_sos(adm, request.user, form.cleaned_data["approve"], form.cleaned_data["notes"])
        messages.success(request, "Validazione registrata.")
    return redirect("clinical:sos_pending")


@permission_required("clinical.view_therapyadministration", raise_exception=True)
def guest_administrations(request, guest_pk):
    guest = _guest(guest_pk)
    qs = TherapyAdministration.all_objects.filter(guest=guest).select_related("therapy__drug", "created_by")
    if request.GET.get("date"):
        qs = qs.filter(shift_date=request.GET["date"])
    return render(request, "clinical/guest_administrations.html", {
        "guest": guest, "administrations": qs[:300], "active_tab": "therapies",
    })


@permission_required("clinical.delete_therapyadministration", raise_exception=True)
def administration_void(request, pk):
    adm = get_object_or_404(TherapyAdministration, pk=pk)
    decision = edit_decision(adm, request.user)
    if not decision.allowed:
        messages.error(request, decision.message)
        return redirect(adm.guest.get_absolute_url())
    form = VoidForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.void_administration(adm, request.user, form.cleaned_data["reason"])
        messages.success(request, "Somministrazione annullata e giacenza ripristinata.")
        return redirect("clinical:guest_administrations", guest_pk=adm.guest_id)
    return render(request, "generic/form.html", {
        "form": form, "guest": adm.guest, "page_title": f"Annulla somministrazione: {adm}",
        "submit_label": "Annulla somministrazione", "cancel_url": adm.guest.get_absolute_url(),
    })


# --- Parametri --------------------------------------------------------------------------------

@permission_required("clinical.view_parameterreading", raise_exception=True)
def guest_parameters(request, guest_pk):
    guest = _guest(guest_pk)
    try:
        days = max(7, min(int(request.GET.get("days", 90)), 3650))
    except ValueError:
        days = 90
    charts = [
        services.chart_series(guest, ptype, days)
        for ptype in ParameterType.objects.filter(active=True, show_chart=True)
    ]
    charts = [c for c in charts if c["points"]]
    readings = guest.parameterreadings.select_related("parameter_type", "created_by")
    if request.GET.get("type"):
        readings = readings.filter(parameter_type_id=request.GET["type"])
    return render(request, "clinical/guest_parameters.html", {
        "guest": guest, "active_tab": "parameters", "charts": charts,
        "readings": readings[:200], "days": days, "types": ParameterType.objects.filter(active=True),
    })


class ParameterCreateView(PermRequiredMixin, RecordCreateMixin, CreateView):
    permission_required = "clinical.add_parameterreading"
    model = ParameterReading
    form_class = ParameterReadingForm
    page_title = "Nuova rilevazione"

    def get_initial(self):
        return {"occurred_at": timezone.localtime(), "parameter_type": self.request.GET.get("type")}


@permission_required("clinical.add_parameterreading", raise_exception=True)
def quick_parameters(request, guest_pk):
    guest = _guest(guest_pk)
    form = QuickParametersForm(request.POST or None, initial={"occurred_at": timezone.localtime()})
    if request.method == "POST" and form.is_valid():
        occurred_at = form.cleaned_data["occurred_at"]
        decision = creation_decision(guest, occurred_at, request.user)
        readings = list(form.readings())
        if not decision.allowed:
            form.add_error(None, decision.message)
        elif not readings:
            form.add_error(None, "Inserire almeno un valore.")
        else:
            for ptype, value, value_2 in readings:
                ParameterReading.objects.create(
                    guest=guest, parameter_type=ptype, value=value, value_2=value_2, occurred_at=occurred_at
                )
            messages.success(request, f"Registrati {len(readings)} parametri.")
            return redirect("clinical:guest_parameters", guest_pk=guest.pk)
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": "Rilevazione parametri", "cancel_url": guest.get_absolute_url(),
        "compact": True,
    })


class ParameterUpdateView(PermRequiredMixin, LockedUpdateMixin, UpdateView):
    permission_required = "clinical.change_parameterreading"
    model = ParameterReading
    form_class = ParameterReadingForm
    page_title = "Modifica rilevazione"

    def get_success_url(self):
        return reverse("clinical:guest_parameters", args=[self.object.guest_id])


# --- Eventi -----------------------------------------------------------------------------------

@permission_required("clinical.view_clinicalevent", raise_exception=True)
def guest_events(request, guest_pk):
    guest = _guest(guest_pk)
    events = ClinicalEvent.all_objects.filter(guest=guest).select_related("created_by")
    if request.GET.get("type"):
        events = events.filter(event_type=request.GET["type"])
    return render(request, "clinical/guest_events.html", {
        "guest": guest, "events": events[:300], "active_tab": "events", "types": ClinicalEvent.EventType.choices,
        "restraints": Restraint.all_objects.filter(guest=guest).select_related("responsible_operator")[:100],
    })


class EventCreateView(PermRequiredMixin, RecordCreateMixin, CreateView):
    permission_required = "clinical.add_clinicalevent"
    model = ClinicalEvent
    form_class = ClinicalEventForm
    page_title = "Nuovo evento sanitario"

    def get_initial(self):
        return {"occurred_at": timezone.localtime(), "event_type": self.request.GET.get("type")}


class EventDetailView(PermRequiredMixin, DetailView):
    permission_required = "clinical.view_clinicalevent"
    model = ClinicalEvent
    template_name = "clinical/event_detail.html"

    def get_queryset(self):
        return ClinicalEvent.all_objects.select_related("guest", "created_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["guest"] = self.object.guest
        context["active_tab"] = "events"
        context["decision"] = edit_decision(self.object, self.request.user)
        return context


class EventUpdateView(PermRequiredMixin, LockedUpdateMixin, UpdateView):
    permission_required = "clinical.change_clinicalevent"
    model = ClinicalEvent
    form_class = ClinicalEventForm
    page_title = "Modifica evento"

    def get_success_url(self):
        return reverse("clinical:event_detail", args=[self.object.pk])


class EventVoidView(VoidRecordView):
    model = ClinicalEvent


@permission_required("clinical.add_clinicalevent", raise_exception=True)
def emergency(request):
    """Pulsante «Evento critico»: registrazione immediata e notifica critica a coordinatori e amministratori."""
    form = EmergencyForm(request.POST or None, initial={"guest": request.GET.get("guest")})
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        decision = creation_decision(event.guest, timezone.now(), request.user)
        if not decision.allowed:
            form.add_error(None, decision.message)
        else:
            event.is_emergency = True
            event.severity = ClinicalEvent.Severity.CRITICAL
            event.occurred_at = timezone.now()
            event.save()
            messages.success(request, "Evento critico registrato. Coordinatori e responsabili sono stati avvisati.")
            return redirect("clinical:event_detail", pk=event.pk)
    return render(request, "clinical/emergency.html", {"form": form})


# --- Contenzioni ------------------------------------------------------------------------------

class RestraintCreateView(PermRequiredMixin, RecordCreateMixin, CreateView):
    permission_required = "clinical.add_restraint"
    model = Restraint
    form_class = RestraintForm
    page_title = "Nuova contenzione"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "guest": self.get_guest()}

    def get_initial(self):
        return {"occurred_at": timezone.localtime(), "authorization_date": timezone.localdate(),
                "responsible_operator": self.request.user}


class RestraintUpdateView(PermRequiredMixin, LockedUpdateMixin, UpdateView):
    permission_required = "clinical.change_restraint"
    model = Restraint
    form_class = RestraintForm
    page_title = "Aggiorna contenzione"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "guest": self.object.guest}

    def get_success_url(self):
        return reverse("clinical:guest_events", args=[self.object.guest_id])


class RestraintVoidView(VoidRecordView):
    model = Restraint


class ParameterVoidView(VoidRecordView):
    model = ParameterReading
