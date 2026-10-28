import datetime

from django.utils import timezone

from .models import Appointment


def send_reminders(now=None):
    """Job: notifiche «visita domani» e «visita oggi» (una sola volta per appuntamento)."""
    from fasas.notifications.services import notify

    now = timezone.localtime(now or timezone.now())
    today = now.date()
    tomorrow = today + datetime.timedelta(days=1)
    sent = 0
    upcoming = Appointment.objects.filter(
        status=Appointment.Status.SCHEDULED, scheduled_at__date__in=[today, tomorrow]
    ).select_related("guest", "companion")
    for appointment in upcoming:
        when = timezone.localtime(appointment.scheduled_at)
        details = f"{appointment.get_kind_display()} alle {when:%H:%M}"
        if appointment.location:
            details += f" presso {appointment.location}"
        if appointment.companion_display:
            details += f". Accompagna: {appointment.companion_display}"
        if appointment.preparation:
            details += f". Preparazione: {appointment.preparation}"
        users = [appointment.companion] if appointment.companion else None
        if when.date() == tomorrow and not appointment.reminded_day_before:
            notify("appointment_tomorrow", f"Visita domani: {appointment.guest} – {appointment.title}", details,
                   link=appointment.get_absolute_url(), guest=appointment.guest, users=users,
                   dedup_key=f"appt-tomorrow-{appointment.pk}")
            appointment.reminded_day_before = True
            appointment.save(update_fields=["reminded_day_before"])
            sent += 1
        elif when.date() == today and not appointment.reminded_same_day:
            notify("appointment_today", f"Visita oggi: {appointment.guest} – {appointment.title}", details,
                   link=appointment.get_absolute_url(), guest=appointment.guest, users=users, level="warning",
                   dedup_key=f"appt-today-{appointment.pk}")
            appointment.reminded_same_day = True
            appointment.save(update_fields=["reminded_same_day"])
            sent += 1
    return {"sent": sent}
