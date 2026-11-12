import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import CreateView, DetailView, UpdateView

from fasas.core.views_mixins import FormPageMixin, PermRequiredMixin
from fasas.guests.models import Guest

from .forms import AppointmentForm, OutcomeForm
from .models import Appointment


@permission_required("appointments.view_appointment", raise_exception=True)
def appointment_list(request):
    today = timezone.localdate()
    period = request.GET.get("period", "upcoming")
    qs = Appointment.objects.select_related("guest", "companion")
    if period == "past":
        qs = qs.filter(scheduled_at__date__lt=today).order_by("-scheduled_at")
    else:
        qs = qs.filter(scheduled_at__date__gte=today, status=Appointment.Status.SCHEDULED)
    if request.GET.get("guest"):
        qs = qs.filter(guest_id=request.GET["guest"])
    if request.GET.get("kind"):
        qs = qs.filter(kind=request.GET["kind"])
    grouped = {}
    for appointment in qs[:300]:
        grouped.setdefault(timezone.localtime(appointment.scheduled_at).date(), []).append(appointment)
    return render(request, "appointments/list.html", {
        "grouped": grouped, "period": period, "kinds": Appointment.Kind.choices, "today": today,
        "tomorrow": today + datetime.timedelta(days=1),
    })


@permission_required("appointments.view_appointment", raise_exception=True)
def guest_appointments(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    return render(request, "appointments/guest_list.html", {
        "guest": guest, "appointments": guest.appointments.order_by("-scheduled_at"), "active_tab": "appointments",
    })


class AppointmentCreateView(PermRequiredMixin, FormPageMixin, CreateView):
    permission_required = "appointments.add_appointment"
    model = Appointment
    form_class = AppointmentForm
    page_title = "Nuovo appuntamento"

    def get_initial(self):
        return {"guest": self.request.GET.get("guest"), "kind": self.request.GET.get("kind")}

    def form_valid(self, form):
        messages.success(self.request, "Appuntamento registrato.")
        return super().form_valid(form)


class AppointmentUpdateView(PermRequiredMixin, FormPageMixin, UpdateView):
    permission_required = "appointments.change_appointment"
    model = Appointment
    form_class = AppointmentForm
    page_title = "Modifica appuntamento"

    def form_valid(self, form):
        # se cambia la data i promemoria vanno reinviati
        if "scheduled_at" in form.changed_data:
            form.instance.reminded_day_before = False
            form.instance.reminded_same_day = False
        return super().form_valid(form)


class AppointmentDetailView(PermRequiredMixin, DetailView):
    permission_required = "appointments.view_appointment"
    model = Appointment
    template_name = "appointments/detail.html"

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "guest": self.object.guest, "active_tab": "appointments"}


@permission_required("appointments.change_appointment", raise_exception=True)
def appointment_outcome(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    form = OutcomeForm(request.POST or None, instance=appointment,
                       initial={"status": Appointment.Status.DONE} if appointment.status == "scheduled" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Esito registrato.")
        return redirect(appointment.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": appointment.guest, "page_title": f"Esito: {appointment}",
        "cancel_url": appointment.get_absolute_url(),
    })
