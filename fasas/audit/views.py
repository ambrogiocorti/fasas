from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView

from fasas.core.views_mixins import PermRequiredMixin

from .models import AuditLog
from .services import registered_models, verify_chain


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


def verify_view(request):
    if not request.user.has_perm("audit.view_auditlog"):
        return redirect("core:dashboard")
    ok, count, broken = verify_chain()
    if ok:
        messages.success(request, f"Catena di integrità verificata: {count} voci, nessuna alterazione.")
    else:
        messages.error(request, f"ATTENZIONE: catena interrotta alla voce #{broken}. Il registro è stato alterato.")
    return redirect("audit:list")
