import datetime
import re

from django.conf import settings
from django.utils import timezone

from fasas.core.middleware import client_ip

from .models import AccessLog


def describe_device(user_agent):
    ua = user_agent or ""
    if re.search(r"iPad|Tablet", ua):
        kind = "Tablet"
    elif re.search(r"Mobi|Android|iPhone", ua):
        kind = "Smartphone"
    else:
        kind = "Computer"
    os_name = next(
        (name for pattern, name in [
            (r"Windows", "Windows"), (r"Android", "Android"), (r"iPhone|iPad|iOS", "iOS"),
            (r"Mac OS X|Macintosh", "macOS"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux"),
        ] if re.search(pattern, ua)),
        "sistema sconosciuto",
    )
    browser = next(
        (name for pattern, name in [
            (r"Edg/", "Edge"), (r"OPR/", "Opera"), (r"Firefox/", "Firefox"),
            (r"Chrome/", "Chrome"), (r"Safari/", "Safari"),
        ] if re.search(pattern, ua)),
        "browser sconosciuto",
    )
    return f"{kind} · {os_name} · {browser}"


def record_access(request, event, username, user=None):
    ua = request.META.get("HTTP_USER_AGENT", "")[:1000] if request is not None else ""
    return AccessLog.objects.create(
        user=user,
        username=(username or "")[:150],
        event=event,
        ip_address=client_ip(request) if request is not None else "",
        user_agent=ua,
        device=describe_device(ua),
    )


def is_locked_out(username, ip=None):
    """Blocco temporaneo dopo troppi tentativi falliti per lo stesso utente o dallo stesso IP."""
    since = timezone.now() - datetime.timedelta(minutes=settings.FASAS_LOGIN_LOCKOUT_MINUTES)
    limit = settings.FASAS_LOGIN_MAX_FAILURES
    recent = AccessLog.objects.filter(timestamp__gte=since)

    failed = [AccessLog.Event.FAILED, AccessLog.Event.OTP_FAILED]  # password e codice di verifica sbagliati
    last_ok = recent.filter(username__iexact=username, event=AccessLog.Event.LOGIN).order_by("-timestamp").first()
    failures = recent.filter(username__iexact=username, event__in=failed)
    if last_ok:
        failures = failures.filter(timestamp__gt=last_ok.timestamp)
    if failures.count() >= limit:
        return True
    if ip:
        return recent.filter(ip_address=ip, event__in=failed).count() >= limit * 3
    return False
