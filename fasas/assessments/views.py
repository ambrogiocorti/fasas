from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from fasas.core.views_mixins import VoidRecordView
from fasas.guests.models import Guest
from fasas.guests.services import guests_in_care

from . import services
from .forms import AssessmentForm
from .models import Assessment
from .scales import SCALES


@permission_required("assessments.view_assessment", raise_exception=True)
def guest_assessments(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    latest = services.latest_by_scale(guest)
    due = {row["scale"].code: row for row in services.due_list(guests=[guest])}
    cards = [{"scale": scale, "setting": setting, "last": latest.get(scale.code), "due": due.get(scale.code)}
             for scale, setting in services.enabled_scales()]
    history = Assessment.all_objects.filter(guest=guest).select_related("created_by").order_by("-occurred_at")[:200]
    return render(request, "assessments/guest.html", {
        "guest": guest, "active_tab": "assessments", "cards": cards, "history": history,
    })


@permission_required("assessments.add_assessment", raise_exception=True)
def assessment_create(request, guest_pk, scale):
    guest = get_object_or_404(Guest, pk=guest_pk)
    definition = SCALES.get(scale)
    if definition is None:
        messages.error(request, "Scala non prevista.")
        return redirect("assessments:guest", guest_pk=guest.pk)
    form = AssessmentForm(request.POST or None, scale=definition)
    if request.method == "POST" and form.is_valid():
        try:
            assessment = services.create_assessment(guest, scale, form.answers(), request.user,
                                                    form.cleaned_data["occurred_at"], form.cleaned_data["notes"])
        except services.AssessmentError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"{definition.name}: {assessment.total} – {assessment.band}.")
            return redirect(assessment.get_absolute_url())
    return render(request, "assessments/form.html", {
        "guest": guest, "form": form, "scale": definition, "page_title": f"{definition.name} – {guest}",
        "cancel_url": reverse("assessments:guest", args=[guest.pk]),
    })


@permission_required("assessments.view_assessment", raise_exception=True)
def assessment_detail(request, pk):
    assessment = get_object_or_404(Assessment.all_objects.select_related("guest", "created_by"), pk=pk)
    return render(request, "assessments/detail.html", {
        "assessment": assessment, "guest": assessment.guest, "active_tab": "assessments",
    })


class AssessmentVoidView(VoidRecordView):
    model = Assessment


@permission_required("assessments.view_assessment", raise_exception=True)
def due_overview(request):
    rows = services.due_list(guests=guests_in_care().filter(status=Guest.Status.ACTIVE))
    return render(request, "assessments/due.html", {"rows": rows, "scales": services.enabled_scales()})


@permission_required("assessments.change_scalesetting", raise_exception=True)
def scale_settings(request):
    configured = services.settings_by_code()
    rows = [(SCALES[code], configured[code]) for code in SCALES]
    if request.method == "POST":
        for scale, setting in rows:
            setting.enabled = request.POST.get(f"enabled_{scale.code}") == "on"
            try:
                setting.interval_days = max(0, min(730, int(request.POST.get(f"interval_{scale.code}") or 0)))
            except ValueError:
                messages.error(request, f"{scale.name}: frequenza non valida.")
                return redirect("assessments:settings")
            setting.save()
        messages.success(request, "Scale di valutazione aggiornate.")
        return redirect("assessments:settings")
    return render(request, "assessments/settings.html", {"rows": rows})
