from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from . import offsite
from .models import BackupRecord, RestoreTest
from .services import copy_offsite, create_backup, verify_backup


@permission_required("backups.manage_backup", raise_exception=True)
def backup_list(request):
    return render(request, "backups/list.html", {
        "backups": BackupRecord.objects.select_related("created_by")[:100],
        "restore_tests": RestoreTest.objects.select_related("created_by")[:12],
        "offsite": offsite.is_configured(), "lock_days": settings.FASAS_OFFSITE_LOCK_DAYS,
    })


@require_POST
@permission_required("backups.manage_backup", raise_exception=True)
def restore_test_run(request):
    from .restore_test import run_restore_test

    test = run_restore_test(request.user)
    level = {"ok": messages.success, "partial": messages.warning}.get(test.result, messages.error)
    level(request, f"Prova di ripristino: {test.get_result_display().lower()}.")
    return redirect("backups:restore_test", pk=test.pk)


@permission_required("backups.manage_backup", raise_exception=True)
def restore_test_detail(request, pk):
    """Verbale stampabile della prova di ripristino."""
    return render(request, "backups/restore_test.html", {"test": get_object_or_404(RestoreTest, pk=pk)})


@require_POST
@permission_required("backups.manage_backup", raise_exception=True)
def backup_run(request):
    record = create_backup(BackupRecord.Kind.MANUAL, request.user)
    if record.status == BackupRecord.Status.OK and verify_backup(record):
        copied = copy_offsite(record)
        messages.success(request, "Backup cifrato creato e verificato" + (
            " e copiato fuori sede." if copied else "; copia fuori sede NON riuscita." if copied is False else "."))
    else:
        messages.error(request, f"Backup non riuscito: {record.error}")
    return redirect("backups:list")


@require_POST
@permission_required("backups.manage_backup", raise_exception=True)
def backup_verify(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    if verify_backup(record):
        messages.success(request, "Integrità del backup verificata.")
    else:
        messages.error(request, record.error)
    return redirect("backups:list")


@permission_required("backups.manage_backup", raise_exception=True)
def backup_download(request, pk):
    """Il file resta cifrato: serve la chiave di backup (conservata fuori dal server) per aprirlo."""
    record = get_object_or_404(BackupRecord, pk=pk, status=BackupRecord.Status.OK, deleted_at__isnull=True)
    if not record.path or not record.path.exists():
        raise Http404
    log_event(AuditLog.Action.DOWNLOAD, record)
    return FileResponse(open(record.path, "rb"), as_attachment=True, filename=record.filename)
