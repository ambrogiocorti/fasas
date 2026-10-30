
import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from fasas import __version__
from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from . import monitoring
from .dashboards import BUILDERS
from .forms import CommunityForm, SystemConfigForm
from .menu import role_of
from .models import ErrorEvent, JobRun, SystemConfig


def dashboard(request):
    """Cruscotto diverso per ogni ruolo: ognuno vede ciò che gli compete (spec. §2)."""
    role = role_of(request.user)
    context = BUILDERS[role](request)
    return render(request, f"core/dashboard_{role}.html", context)


@permission_required("core.change_systemconfig", raise_exception=True)
def system_config(request):
    config = SystemConfig.get()
    form = SystemConfigForm(request.POST or None, instance=config, prefix="cfg")
    community_form = CommunityForm(request.POST or None, instance=config.community, prefix="com")
    if request.method == "POST" and form.is_valid() and community_form.is_valid():
        community_form.save()
        form.save()
        log_event(AuditLog.Action.CONFIG, config, changes={"campi": [None, ", ".join(form.changed_data)]})
        messages.success(request, "Configurazione salvata.")
        return redirect("core:config")
    return render(request, "core/config.html", {"form": form, "community_form": community_form})


@transaction.non_atomic_requests  # deve rispondere 503 anche quando il database non c'è
def health(request):
    """
    Controllo di stato per un servizio di monitoraggio: 503 se database o dischi non funzionano.
    Il dettaglio dei controlli solo con FASAS_HEALTH_TOKEN (nessun dato sanitario in ogni caso).
    """
    results = monitoring.checks()
    status = monitoring.overall(results)
    body = {"status": status, "version": __version__}
    token = settings.FASAS_HEALTH_TOKEN
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.GET.get("token", "")
    if token and given and hmac.compare_digest(given, token):
        body["checks"] = {name: {"status": state, "detail": detail} for name, state, detail in results}
    return JsonResponse(body, status=503 if status == "error" else 200)


@permission_required("core.view_errorevent", raise_exception=True)
def error_list(request):
    if request.method == "POST" and request.user.has_perm("core.change_errorevent"):
        ErrorEvent.objects.filter(pk=request.POST.get("pk"), resolved_at__isnull=True).update(resolved_at=timezone.now())
        messages.success(request, "Errore segnato come risolto: se si ripresenta torna in elenco.")
        return redirect("core:errors")
    return render(request, "core/errors.html", {
        "errors": ErrorEvent.objects.all()[:200], "checks": monitoring.checks(),
        "jobs": JobRun.objects.all(), "intervals": monitoring.JOB_INTERVALS,
    })


def settings_hub(request):
    """Pagina indice delle configurazioni visibili all'utente."""
    return render(request, "core/settings_hub.html")
