from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.models import Community
from fasas.core.views_mixins import FormPageMixin, PermRequiredMixin

from . import services
from .dashboard import TIMELINE_KINDS, clinical_dashboard, timeline
from .forms import AllergyForm, DiagnosisForm, DischargeForm, GuestContactForm, GuestForm, MovementForm
from .models import Allergy, ClinicalTag, Diagnosis, Guest, GuestContact


@permission_required("guests.view_guest", raise_exception=True)
def guest_list(request):
    status = request.GET.get("status", "in_care")
    qs = Guest.objects.prefetch_related("tags").annotate(
        open_protocols=Count("protocol_activations", filter=Q(protocol_activations__status__in=["open", "in_progress"]),
                             distinct=True),
        allergy_count=Count("allergies", distinct=True),
    )
    if status == "in_care":
        qs = qs.exclude(status=Guest.Status.ARCHIVED)
    elif status in Guest.Status.values:
        qs = qs.filter(status=status)
    tag_ids = [t for t in request.GET.getlist("tag") if t.isdigit()]
    for tag_id in tag_ids:
        qs = qs.filter(tags__pk=tag_id)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(fiscal_code__icontains=q) | Q(room__icontains=q))
    return render(request, "guests/list.html", {
        "guests": qs.distinct(), "tags": ClinicalTag.objects.all(), "selected_tags": [int(t) for t in tag_ids],
        "status": status, "statuses": Guest.Status.choices, "q": q,
    })


class GuestCreateView(PermRequiredMixin, FormPageMixin, CreateView):
    permission_required = "guests.add_guest"
    model = Guest
    form_class = GuestForm
    page_title = "Nuovo ospite – apertura cartella FASAS"

    def form_valid(self, form):
        form.instance.community = Community.default()
        response = super().form_valid(form)
        from .models import AdmissionEvent

        AdmissionEvent.objects.create(guest=self.object, kind=AdmissionEvent.Kind.ADMISSION,
                                      date=self.object.admission_date)
        messages.success(self.request, "Cartella aperta. Completare dati sanitari, allergie e contatti.")
        return response


class GuestUpdateView(PermRequiredMixin, FormPageMixin, UpdateView):
    permission_required = "guests.change_guest"
    model = Guest
    form_class = GuestForm

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().is_archived:
            messages.error(request, "Cartella archiviata: le modifiche sono bloccate.")
            return redirect(self.get_object().get_absolute_url())
        return super().dispatch(request, *args, **kwargs)

    def get_page_title(self):
        return f"Modifica anagrafica – {self.object}"

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "guest": self.object}


@permission_required("guests.view_guest", raise_exception=True)
def guest_detail(request, pk):
    guest = get_object_or_404(Guest.objects.prefetch_related("tags"), pk=pk)
    log_event(AuditLog.Action.VIEW, guest)
    return render(request, "guests/detail.html", {"guest": guest, "active_tab": "dashboard", **clinical_dashboard(guest)})


@permission_required("guests.view_guest", raise_exception=True)
def guest_health(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    return render(request, "guests/health.html", {
        "guest": guest, "active_tab": "health",
        "diagnoses": guest.diagnoses.all(), "allergies": guest.allergies.all(), "contacts": guest.contacts.all(),
        "movements": guest.admission_events.all(),
    })


@permission_required("guests.view_guest", raise_exception=True)
def guest_timeline(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    kinds = request.GET.getlist("kind") or None
    return render(request, "guests/timeline.html", {
        "guest": guest, "active_tab": "timeline", "items": timeline(guest, kinds),
        "kinds": TIMELINE_KINDS, "selected": kinds or [],
    })


def _child_view(request, guest_pk, model, form_class, perm, title, pk=None):
    if not request.user.has_perm(perm):
        raise PermissionDenied
    guest = get_object_or_404(Guest, pk=guest_pk)
    if guest.is_archived:
        messages.error(request, "Cartella archiviata: le modifiche sono bloccate.")
        return redirect("guests:health", pk=guest.pk)
    instance = get_object_or_404(model, pk=pk, guest=guest) if pk else None
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.guest = guest
        obj.save()
        messages.success(request, "Salvato.")
        return redirect("guests:health", pk=guest.pk)
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": title, "cancel_url": reverse("guests:health", args=[guest.pk]),
    })


def contact_edit(request, guest_pk, pk=None):
    perm = "guests.change_guestcontact" if pk else "guests.add_guestcontact"
    return _child_view(request, guest_pk, GuestContact, GuestContactForm, perm, "Contatto / tutela legale", pk)


def diagnosis_edit(request, guest_pk, pk=None):
    perm = "guests.change_diagnosis" if pk else "guests.add_diagnosis"
    return _child_view(request, guest_pk, Diagnosis, DiagnosisForm, perm, "Diagnosi / patologia", pk)


def allergy_edit(request, guest_pk, pk=None):
    perm = "guests.change_allergy" if pk else "guests.add_allergy"
    return _child_view(request, guest_pk, Allergy, AllergyForm, perm, "Allergia / intolleranza", pk)


@permission_required("guests.archive_guest", raise_exception=True)
def guest_discharge(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    if guest.is_archived:
        messages.info(request, "La cartella è già archiviata.")
        return redirect(guest.get_absolute_url())
    form = DischargeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.discharge_and_archive(guest, request.user, form.cleaned_data["date"], form.cleaned_data["reason"],
                                       form.cleaned_data["destination"])
        messages.success(request, "Ospite dimesso: cartella archiviata e bloccata.")
        return redirect(guest.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": f"Dimissione e archiviazione – {guest}", "submit_label": "Dimetti e archivia",
        "cancel_url": guest.get_absolute_url(), "danger": True,
        "intro": "Le terapie attive verranno terminate e la cartella diventerà di sola consultazione. "
                 "Prima della dimissione è consigliato esportare la cartella completa in PDF.",
    })


@permission_required("guests.add_admissionevent", raise_exception=True)
def guest_movement(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    form = MovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.register_movement(guest, form.cleaned_data["kind"], form.cleaned_data["date"], form.cleaned_data["notes"])
        except services.ArchivedGuestError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Movimento registrato.")
        return redirect("guests:health", pk=guest.pk)
    return render(request, "generic/form.html", {
        "form": form, "guest": guest, "page_title": "Ricovero, assenza o rientro", "cancel_url": guest.get_absolute_url(),
    })


@require_POST
@permission_required("guests.change_guest", raise_exception=True)
def toggle_tag(request, pk, tag_pk):
    guest = get_object_or_404(Guest, pk=pk)
    services.ensure_not_archived(guest)
    tag = get_object_or_404(ClinicalTag, pk=tag_pk)
    if guest.tags.filter(pk=tag.pk).exists():
        guest.tags.remove(tag)
    else:
        guest.tags.add(tag)
    return redirect(guest.get_absolute_url())
