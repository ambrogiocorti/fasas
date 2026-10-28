from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from fasas.core.views_mixins import FormPageMixin, PermRequiredMixin

from . import engine
from .forms import ActionDoneForm, ProtocolForm, ResolveForm
from .models import Protocol, ProtocolActionLog, ProtocolActivation


class ProtocolListView(PermRequiredMixin, ListView):
    permission_required = "protocols.view_protocol"
    model = Protocol
    template_name = "protocols/protocol_list.html"


class ProtocolCreateView(PermRequiredMixin, FormPageMixin, CreateView):
    permission_required = "protocols.add_protocol"
    model = Protocol
    form_class = ProtocolForm
    page_title = "Nuovo protocollo"
    success_url = reverse_lazy("protocols:list")

    def get_initial(self):
        return {"kind": self.request.GET.get("kind")}


class ProtocolUpdateView(PermRequiredMixin, FormPageMixin, UpdateView):
    permission_required = "protocols.change_protocol"
    model = Protocol
    form_class = ProtocolForm
    success_url = reverse_lazy("protocols:list")

    def get_page_title(self):
        return f"Protocollo: {self.object}"


@permission_required("protocols.view_protocolactivation", raise_exception=True)
def activation_list(request):
    qs = ProtocolActivation.objects.select_related("protocol", "guest", "resolved_by")
    status = request.GET.get("status", "open")
    if status == "open":
        qs = qs.filter(status__in=ProtocolActivation.OPEN_STATES)
    elif status in ProtocolActivation.Status.values:
        qs = qs.filter(status=status)
    if request.GET.get("guest"):
        qs = qs.filter(guest_id=request.GET["guest"])
    if request.GET.get("kind"):
        qs = qs.filter(protocol__kind=request.GET["kind"])
    return render(request, "protocols/activation_list.html", {
        "activations": qs[:300], "status": status, "kinds": Protocol.Kind.choices,
    })


@permission_required("protocols.view_protocolactivation", raise_exception=True)
def activation_detail(request, pk):
    activation = get_object_or_404(ProtocolActivation.objects.select_related("protocol", "guest"), pk=pk)
    return render(request, "protocols/activation_detail.html", {
        "activation": activation, "guest": activation.guest, "actions": activation.actions_status(),
        "resolve_form": ResolveForm(), "can_handle": request.user.has_perm("protocols.change_protocolactivation"),
    })


@require_POST
@permission_required("protocols.change_protocolactivation", raise_exception=True)
def action_done(request, pk):
    activation = get_object_or_404(ProtocolActivation, pk=pk)
    form = ActionDoneForm(request.POST)
    if activation.is_open and form.is_valid():
        ProtocolActionLog.objects.create(
            activation=activation, action_label=form.cleaned_data["action_label"][:255],
            done_by=request.user, notes=form.cleaned_data["notes"],
        )
        if activation.status == ProtocolActivation.Status.OPEN:
            activation.status = ProtocolActivation.Status.IN_PROGRESS
            activation.save(update_fields=["status"])
        messages.success(request, "Azione registrata.")
    return redirect(activation.get_absolute_url())


@require_POST
@permission_required("protocols.change_protocolactivation", raise_exception=True)
def activation_resolve(request, pk):
    activation = get_object_or_404(ProtocolActivation, pk=pk)
    form = ResolveForm(request.POST)
    if activation.is_open and form.is_valid():
        engine.resolve(activation, request.user, form.cleaned_data["notes"], status=form.cleaned_data["status"])
        messages.success(request, "Protocollo chiuso.")
    return redirect(activation.get_absolute_url())
