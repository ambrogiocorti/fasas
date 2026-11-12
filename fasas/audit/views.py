from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from fasas.core.views_mixins import PermRequiredMixin

from .anchoring import create_checkpoint, receipt_zip
from .models import AuditCheckpoint, AuditLog
from .services import log_event, registered_models


class AuditLogListView(PermRequiredMixin, ListView):
    permission_required = "audit.view_auditlog"
    template_name = "audit/auditlog_list.html"
    paginate_by = 100

    def get_queryset(self):
        qs = AuditLog.objects.select_related("content_type")
        p = self.request.GET
        if p.get("user"):
            qs = qs.filter(username__icontains=p["user"])
        if p.get("action"):
            qs = qs.filter(action=p["action"])
        if p.get("model"):
            qs = qs.filter(content_type_id=p["model"])
        if p.get("guest"):
            qs = qs.filter(guest_id=p["guest"])
        if p.get("object_id"):
            qs = qs.filter(object_id=p["object_id"])
        if p.get("date_from"):
            qs = qs.filter(timestamp__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(timestamp__date__lte=p["date_to"])
        if p.get("q"):
            qs = qs.filter(object_repr__icontains=p["q"])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = AuditLog.Action.choices
        context["models"] = sorted(
            (ContentType.objects.get_for_model(m) for m in registered_models()), key=lambda ct: ct.name
        )
        return context


class AuditLogDetailView(PermRequiredMixin, DetailView):
    permission_required = "audit.view_auditlog"
    model = AuditLog
    template_name = "audit/auditlog_detail.html"


@require_POST
def verify_view(request):
    if not request.user.has_perm("audit.view_auditlog"):
        return redirect("core:dashboard")
    checkpoint = create_checkpoint("manuale")
    if checkpoint.chain_ok:
        stamp = " e marcato temporalmente" if checkpoint.timestamped else " (senza marca temporale: nessuna TSA)"
        messages.success(request, f"Catena di integrità verificata: {checkpoint.entries} voci, nessuna alterazione. "
                                  f"Punto di controllo salvato{stamp}.")
    elif checkpoint.broken_at:
        messages.error(request, f"ATTENZIONE: catena interrotta alla voce #{checkpoint.broken_at}. Il registro è stato alterato.")
    else:
        messages.error(request, "ATTENZIONE: voci già ancorate hanno oggi un'impronta diversa: la storia è stata riscritta.")
    return redirect("audit:checkpoints")


def checkpoint_list(request):
    if not request.user.has_perm("audit.view_auditlog"):
        return redirect("core:dashboard")
    checkpoints = AuditCheckpoint.objects.all()[:100]
    return render(request, "audit/checkpoints.html", {
        "checkpoints": checkpoints, "tsa": bool(settings.FASAS_SIGNATURE_TSA_URL) and settings.FASAS_AUDIT_TIMESTAMP,
    })


def checkpoint_receipt(request, pk):
    if not request.user.has_perm("audit.view_auditlog"):
        return redirect("core:dashboard")
    checkpoint = get_object_or_404(AuditCheckpoint, pk=pk)
    log_event(AuditLog.Action.DOWNLOAD, checkpoint, repr_text=f"Ricevuta punto di controllo audit #{checkpoint.pk}")
    response = HttpResponse(receipt_zip(checkpoint), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="audit-punto-di-controllo-{checkpoint.pk}.zip"'
    return response
