from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from .models import BackupRecord
from .services import create_backup, verify_backup


@permission_required("backups.manage_backup", raise_exception=True)
def backup_list(request):
    return render(request, "backups/list.html", {"backups": BackupRecord.objects.select_related("created_by")[:100]})


@require_POST
@permission_required("backups.manage_backup", raise_exception=True)
def backup_run(request):
    record = create_backup(BackupRecord.Kind.MANUAL, request.user)
    if record.status == BackupRecord.Status.OK and verify_backup(record):
        messages.success(request, "Backup cifrato creato e verificato.")
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
