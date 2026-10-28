import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from .forms import CommunityForm, SystemConfigForm
from .models import SystemConfig
from .shifts import Shift, resolve_shift, shift_bounds


def dashboard(request):
    """Cruscotto del turno: cosa c'è da fare adesso, per tutti i ruoli; in più lo stato sistema per l'admin."""
    from fasas.appointments.models import Appointment
    from fasas.backups.models import BackupRecord
    from fasas.clinical.models import ClinicalEvent, Restraint, TherapyAdministration
    from fasas.clinical.services import scheduled_doses
    from fasas.daily.models import DiaryEntry, ShiftAssignment
    from fasas.daily.services import checklist_status, is_shift_closed
    from fasas.guests.models import Guest
    from fasas.guests.services import guests_in_care
    from fasas.notifications.services import unread_for
    from fasas.pharmacy.services import drug_stock_summary
    from fasas.protocols.engine import open_activations

    user = request.user
    day, shift = resolve_shift()
    start, end = shift_bounds(day, shift)
    now = timezone.now()
    today = timezone.localdate()
    guests = guests_in_care()
    context = {"day": day, "shift": shift, "shift_label": Shift(shift).label, "shift_start": start, "shift_end": end,
               "guest_count": guests.filter(status=Guest.Status.ACTIVE).count(),
               "absent_count": guests.filter(status=Guest.Status.HOSPITALIZED).count()}

    if user.has_perm("clinical.view_therapyadministration"):
        doses = scheduled_doses(day, shift, guests)
        context.update({
            "doses_total": len(doses), "doses_done": sum(1 for d in doses if d.done),
            "doses_due": [d for d in doses if not d.done and d.moment <= now + datetime.timedelta(minutes=60)][:12],
            "sos_pending": TherapyAdministration.objects.filter(
                is_sos=True, validation_status=TherapyAdministration.Validation.PENDING).count()
            if user.has_perm("clinical.validate_sos") else None,
        })
    if user.has_perm("daily.view_checklistcheck"):
        status = checklist_status(day, shift)
        context.update({"checklist_total": status["total"], "checklist_done": status["done"]})
    context.update({
        "protocols": open_activations()[:10] if user.has_perm("protocols.view_protocolactivation") else [],
        "events": ClinicalEvent.objects.filter(occurred_at__gte=now - datetime.timedelta(hours=24))
        .select_related("guest")[:8] if user.has_perm("clinical.view_clinicalevent") else [],
        "restraints": Restraint.objects.filter(ended_at__isnull=True).select_related("guest")
        if user.has_perm("clinical.view_restraint") else [],
        "appointments": Appointment.objects.filter(
            status=Appointment.Status.SCHEDULED, scheduled_at__date__in=[today, today + datetime.timedelta(days=1)]
        ).select_related("guest", "companion") if user.has_perm("appointments.view_appointment") else [],
        "relevant_diary": DiaryEntry.objects.filter(is_relevant=True, occurred_at__gte=now - datetime.timedelta(hours=48))
        .select_related("guest", "created_by")[:5] if user.has_perm("daily.view_diaryentry") else [],
        "notifications": unread_for(user)[:6],
        "on_shift": ShiftAssignment.objects.filter(date=day, shift=shift).select_related("user"),
        "checked_in": ShiftAssignment.objects.filter(date=day, shift=shift, user=user, checked_in_at__isnull=False).exists(),
        "shift_closed": is_shift_closed(day, shift),
    })
    if user.has_perm("pharmacy.view_stocklot"):
        stock = drug_stock_summary()
        context["stock_low"] = [r for r in stock if r["low"]][:6]
        context["stock_expiring"] = sum(len(r["expiring"]) + len(r["expired"]) for r in stock)
    if user.has_perm("backups.manage_backup"):
        context["last_backup"] = BackupRecord.objects.first()
        context["audit_count"] = AuditLog.objects.count()
    return render(request, "core/dashboard.html", context)


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
