import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from fasas.documents.services import DocumentLockedError
from fasas.guests.models import Guest

from . import services
from .forms import GoalVerificationForm, PAIForm, PAIGoalForm
from .models import PAI, PAIGoal


@permission_required("pai.view_pai", raise_exception=True)
def guest_pai(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    pais = guest.pais.select_related("approved_by")
    current = pais.filter(status=PAI.Status.ACTIVE).first() or pais.first()
    if current:
        return redirect(current.get_absolute_url())
    return render(request, "pai/empty.html", {"guest": guest, "active_tab": "pai"})


@require_POST
@permission_required("pai.add_pai", raise_exception=True)
def pai_create(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    try:
        pai = services.create_first(guest, request.user, timezone.localdate() + datetime.timedelta(days=180))
    except services.PAIError as exc:
        messages.error(request, str(exc))
        return redirect("pai:guest", guest_pk=guest.pk)
    messages.success(request, "Bozza di PAI creata: aggiungere gli obiettivi per ogni area.")
    return redirect(pai.get_absolute_url())


@permission_required("pai.view_pai", raise_exception=True)
def pai_detail(request, pk):
    pai = get_object_or_404(PAI.objects.select_related("guest", "approved_by", "document"), pk=pk)
    goals = pai.goals.select_related("responsible")
    areas = [(code, label, [g for g in goals if g.area == code]) for code, label in PAIGoal.Area.choices]
    return render(request, "pai/detail.html", {
        "pai": pai, "guest": pai.guest, "areas": areas, "active_tab": "pai",
        "history": pai.guest.pais.order_by("-version"),
    })


def _editable(pai, user, perm="pai.change_pai"):
    if not user.has_perm(perm):
        raise PermissionDenied
    if not pai.is_editable:
        raise PermissionDenied("Solo le bozze sono modificabili: creare una revisione.")


@permission_required("pai.change_pai", raise_exception=True)
def pai_edit(request, pk):
    pai = get_object_or_404(PAI, pk=pk)
    _editable(pai, request.user)
    form = PAIForm(request.POST or None, instance=pai)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(pai.get_absolute_url())
    return render(request, "generic/form.html", {"form": form, "guest": pai.guest, "page_title": f"{pai}: dati generali",
                                                 "cancel_url": pai.get_absolute_url()})


@permission_required("pai.change_pai", raise_exception=True)
def goal_edit(request, pk, goal_pk=None):
    pai = get_object_or_404(PAI, pk=pk)
    _editable(pai, request.user)
    goal = get_object_or_404(PAIGoal, pk=goal_pk, pai=pai) if goal_pk else None
    form = PAIGoalForm(request.POST or None, instance=goal, initial={"area": request.GET.get("area")})
    if request.method == "POST" and form.is_valid():
        goal = form.save(commit=False)
        goal.pai = pai
        goal.save()
        messages.success(request, "Obiettivo salvato.")
        return redirect(pai.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": pai.guest, "page_title": "Obiettivo PAI", "cancel_url": pai.get_absolute_url(),
    })


@require_POST
@permission_required("pai.change_pai", raise_exception=True)
def goal_delete(request, pk, goal_pk):
    pai = get_object_or_404(PAI, pk=pk)
    _editable(pai, request.user)
    get_object_or_404(PAIGoal, pk=goal_pk, pai=pai).delete()
    messages.success(request, "Obiettivo rimosso dalla bozza.")
    return redirect(pai.get_absolute_url())


@permission_required("pai.change_paigoal", raise_exception=True)
def goal_verify(request, pk, goal_pk):
    """Verifica periodica di un obiettivo del PAI in vigore."""
    pai = get_object_or_404(PAI, pk=pk)
    if pai.guest.is_archived:
        raise PermissionDenied
    goal = get_object_or_404(PAIGoal, pk=goal_pk, pai=pai)
    form = GoalVerificationForm(request.POST or None, instance=goal)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Verifica registrata.")
        return redirect(pai.get_absolute_url())
    return render(request, "generic/form.html", {
        "form": form, "guest": pai.guest, "page_title": f"Verifica obiettivo: {goal}", "cancel_url": pai.get_absolute_url(),
    })


@require_POST
@permission_required("pai.add_pai", raise_exception=True)
def pai_revise(request, pk):
    pai = get_object_or_404(PAI, pk=pk)
    try:
        revision = services.create_revision(pai, request.user)
    except services.PAIError as exc:
        messages.error(request, str(exc))
        return redirect(pai.get_absolute_url())
    messages.success(request, f"Creata la bozza di revisione v{revision.version}.")
    return redirect(revision.get_absolute_url())


@require_POST
def pai_activate(request, pk):
    pai = get_object_or_404(PAI, pk=pk)
    try:
        services.activate(pai, request.user)
        services.archive_pdf(pai, request.user)
    except services.PAIError as exc:
        messages.error(request, str(exc))
    except DocumentLockedError as exc:
        messages.warning(request, f"PAI in vigore, ma il PDF non è stato rigenerato: {exc.message}")
    else:
        messages.success(request, "PAI in vigore. Il PDF è stato archiviato nei documenti e può essere firmato.")
    return redirect(pai.get_absolute_url())


@require_POST
@permission_required("pai.change_pai", raise_exception=True)
def pai_pdf(request, pk):
    pai = get_object_or_404(PAI, pk=pk)
    if pai.guest.is_archived and pai.document_id:
        return redirect(pai.document.get_absolute_url())
    try:
        document = services.archive_pdf(pai, request.user)
    except DocumentLockedError as exc:
        messages.error(request, exc.message)
        return redirect(pai.document.get_absolute_url())
    messages.success(request, "PDF del PAI generato e archiviato.")
    return redirect(document.get_absolute_url())
