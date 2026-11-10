
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
    if role == "family":
        return redirect("families:home")
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


@permission_required("core.change_systemconfig", raise_exception=True)
def modules_view(request):
    """Moduli accendibili: uno per uno, oppure tutti insieme («configurazione per il pilota», «accendi tutto»)."""
    from . import modules

    config = SystemConfig.get()
    if request.method == "POST":
        action = request.POST.get("action")
        before = modules.disabled(config)
        if action == "pilot":
            off = set(modules.PILOT_OFF)
        elif action == "all":  # tranne i moduli da accendere apposta (area familiari: parere del DPO)
            off = set(modules.DEFAULT_OFF)
        else:
            chosen = set(request.POST.getlist("on"))
            off = {m.key for m in modules.MODULES if m.key not in chosen}
        if off != before:
            config.disabled_modules = sorted(off)
            config.save(update_fields=["disabled_modules", "updated_at"])
            log_event(AuditLog.Action.CONFIG, config, changes={"moduli spenti": [
                ", ".join(sorted(before)) or None, ", ".join(sorted(off)) or None]})
            messages.success(request, "Moduli aggiornati." if off - modules.DEFAULT_OFF else "Tutti i moduli sono accesi.")
        else:
            messages.info(request, "Nessuna modifica.")
        return redirect("core:modules")
    off = modules.disabled(config)
    return render(request, "core/modules.html", {
        "modules_list": [{"module": m, "on": m.key not in off} for m in modules.MODULES],
        "pilot_off": [m for m in modules.MODULES if not m.pilot],
    })


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
    return render(request, "core/settings_hub.html", {"version": __version__})
