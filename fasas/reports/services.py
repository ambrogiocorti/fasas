import datetime

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import delete_stored, read_encrypted, sha256, store_encrypted
from fasas.core.models import SystemConfig

from . import generators
from .models import GeneratedReport, ReportFormat, ReportSchedule, ReportType


def _expires(years, from_date=None):
    from_date = from_date or timezone.localdate()
    try:
        return from_date.replace(year=from_date.year + years)
    except ValueError:  # 29 febbraio
        return from_date.replace(year=from_date.year + years, day=28)


def store_report(data, title, report_type, fmt, user=None, guest=None, start=None, end=None, schedule=None,
                 retention_years=None):
    retention_years = retention_years or SystemConfig.get().report_retention_years
    ext = "pdf" if fmt == ReportFormat.PDF else "xlsx"
    slug = title.lower().replace(" ", "_").replace("/", "-")[:60]
    period = f"_{start:%Y%m%d}-{end:%Y%m%d}" if start and end else ""
    report = GeneratedReport.objects.create(
        schedule=schedule, report_type=report_type, format=fmt, title=title, period_start=start, period_end=end,
        guest=guest, storage_name=store_encrypted(data, "reports"), filename=f"{slug}{period}.{ext}",
        size=len(data), sha256=sha256(data), generated_by=user, expires_on=_expires(retention_years),
    )
    log_event(AuditLog.Action.EXPORT, report, user=user, guest=guest,
              changes={"report": [None, title], "periodo": [None, f"{start} – {end}"]})
    return report


def generate_report(report_type, fmt, start, end, guest=None, user=None, schedule=None, retention_years=None):
    data, content = generators.render(report_type, fmt, start, end, guest, user)
    title = data.title + (f" – {guest}" if guest else "")
    return store_report(content, title, report_type, fmt, user, guest, start, end, schedule, retention_years)


def read_report(report, user=None):
    data = read_encrypted(report.storage_name)
    if sha256(data) != report.sha256:
        raise ValueError("Il report non corrisponde all'impronta registrata.")
    log_event(AuditLog.Action.DOWNLOAD, report, user=user, guest=report.guest)
    return data


def previous_period(frequency, today):
    if frequency == ReportSchedule.Frequency.DAILY:
        day = today - datetime.timedelta(days=1)
        return day, day
    if frequency == ReportSchedule.Frequency.WEEKLY:
        start = today - datetime.timedelta(days=today.weekday() + 7)
        return start, start + datetime.timedelta(days=6)
    first_this_month = today.replace(day=1)
    end = first_this_month - datetime.timedelta(days=1)
    return end.replace(day=1), end


def run_due_schedules(today=None):
    """Job: genera i report programmati del periodo concluso (una sola volta per periodo)."""
    from fasas.notifications.services import notify

    today = today or timezone.localdate()
    generated = 0
    for schedule in ReportSchedule.objects.filter(active=True).select_related("guest"):
        start, end = previous_period(schedule.frequency, today)
        if GeneratedReport.objects.filter(schedule=schedule, period_start=start, period_end=end).exists():
            continue
        try:
            with transaction.atomic():
                report = generate_report(schedule.report_type, schedule.format, start, end, schedule.guest,
                                         schedule=schedule, retention_years=schedule.retention_years)
        except IntegrityError:
            continue
        schedule.last_run_at = timezone.now()
        schedule.save(update_fields=["last_run_at"])
        generated += 1
        notify("report_ready", f"Report disponibile: {report.title}",
               f"Periodo {start:%d/%m/%Y} – {end:%d/%m/%Y}", link=reverse("reports:list"), dedup_key=f"report-{report.pk}")
    return {"generated": generated}


def purge_expired_reports(today=None):
    """Job: elimina i report oltre il periodo di conservazione (1–5 anni), lasciandone traccia nell'audit."""
    today = today or timezone.localdate()
    removed = 0
    for report in GeneratedReport.objects.filter(expires_on__lt=today):
        log_event(AuditLog.Action.DELETE, report, reason="Scadenza del periodo di conservazione",
                  changes={"report": [report.title, None], "sha256": [report.sha256, None]})
        delete_stored(report.storage_name)
        report.delete()
        removed += 1
    return {"removed": removed}


REPORT_TYPES = ReportType.choices
