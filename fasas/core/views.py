
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from .dashboards import BUILDERS
from .forms import CommunityForm, SystemConfigForm
from .menu import role_of
from .models import SystemConfig


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


def health(request):
    """Controllo di stato per il monitoraggio (nessun dato sensibile)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({"status": "ok" if db_ok else "error", "database": db_ok}, status=200 if db_ok else 503)


def settings_hub(request):
    """Pagina indice delle configurazioni visibili all'utente."""
    return render(request, "core/settings_hub.html")
