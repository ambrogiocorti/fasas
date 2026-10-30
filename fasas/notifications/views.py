import json

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from fasas.accounts.models import Role

from . import push
from .models import (
    DEFAULT_ROLES,
    REQUIRED_PERMISSION,
    Notification,
    NotificationKind,
    NotificationSetting,
    PushSubscription,
)
from .services import ensure_default_settings, setting_for, unread_for


def notification_list(request):
    qs = Notification.objects.filter(recipient=request.user).select_related("guest")
    if request.GET.get("unread"):
        qs = qs.filter(read_at__isnull=True)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page_obj": page, "notifications": page.object_list})


@require_POST
def mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    target = notification.link if request.POST.get("open") and notification.link else request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = ""
    return redirect(target or "notifications:list")


@require_POST
def mark_all_read(request):
    unread_for(request.user).update(read_at=timezone.now())
    messages.success(request, "Tutte le notifiche sono state segnate come lette.")
    return redirect("notifications:list")


def unread_count(request):
    unread = unread_for(request.user)
    latest_critical = unread.filter(level=Notification.Level.CRITICAL).order_by("-created_at").first()
    return JsonResponse({
        "count": unread.count(),
        "critical": {
            "id": latest_critical.pk, "title": latest_critical.title, "message": latest_critical.message[:200],
        } if latest_critical else None,
    })


@permission_required("notifications.change_notificationsetting", raise_exception=True)
def notification_settings(request):
    ensure_default_settings()
    settings_list = list(NotificationSetting.objects.all())
    if request.method == "POST":
        for setting in settings_list:
            setting.enabled = bool(request.POST.get(f"enabled_{setting.pk}"))
            setting.send_email = bool(request.POST.get(f"email_{setting.pk}"))
            setting.send_push = bool(request.POST.get(f"push_{setting.pk}"))
            setting.roles = [r for r in Role.values if request.POST.get(f"role_{setting.pk}_{r}")]
            setting.save()
        messages.success(request, "Impostazioni notifiche salvate.")
        return redirect("notifications:settings")
    return render(request, "notifications/settings.html", {
        "settings_list": settings_list, "roles": Role.choices, "push_enabled": push.is_enabled(),
    })


def open_notification(request, pk):
    """Destinazione del tocco su una notifica push: la segna come letta e apre il collegamento."""
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    target = notification.link
    if not target or not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect("notifications:list")
    return redirect(target)


PUSH_CHECKS = [
    ("secure", "Pagina aperta in modo sicuro (HTTPS o 127.0.0.1)"),
    ("support", "Browser compatibile con le notifiche push"),
    ("permission", "Permesso alle notifiche concesso al FASAS"),
    ("worker", "Service worker del FASAS attivo"),
    ("subscription", "Questo browser è collegato al tuo utente"),
]


def push_kinds_for(user):
    """Avvisi che arrivano a questo utente anche come notifica push, secondo le impostazioni attuali."""
    kinds = []
    for kind in NotificationKind:
        setting = setting_for(kind)
        personal = not DEFAULT_ROLES.get(kind, ["admin"])  # es. turni: inviati alla persona interessata
        if not (setting.enabled and setting.send_push) or not (personal or user.role in setting.roles):
            continue
        if REQUIRED_PERMISSION.get(kind) and not user.has_perm(REQUIRED_PERMISSION[kind]):
            continue
        kinds.append({"label": kind.label, "personal": personal and user.role not in setting.roles})
    return kinds


def devices(request):
    subscriptions = list(PushSubscription.objects.filter(user=request.user))
    for subscription in subscriptions:
        subscription.service = push.service_name(subscription.endpoint)
    return render(request, "notifications/devices.html", {
        "subscriptions": subscriptions, "push_enabled": push.is_enabled(), "public_key": push.public_key(),
        "endpoint_hashes": [push.endpoint_hash(s.endpoint) for s in subscriptions],
        "push_kinds": push_kinds_for(request.user), "push_checks": PUSH_CHECKS,
        "can_configure": request.user.has_perm("notifications.change_notificationsetting"),
    })


def _device_label(user_agent):
    ua = user_agent.lower()
    system = next((name for key, name in [("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"),
                                           ("windows", "Windows"), ("mac os", "Mac"), ("linux", "Linux")] if key in ua), "")
    browser = next((name for key, name in [("edg/", "Edge"), ("firefox", "Firefox"), ("chrome", "Chrome"),
                                            ("safari", "Safari")] if key in ua), "browser")
    return f"{browser} su {system}" if system else browser


@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body)
        endpoint, keys = data["endpoint"], data["keys"]
        p256dh, auth = keys["p256dh"], keys["auth"]
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("Iscrizione non valida")
    if not str(endpoint).startswith("https://") or len(endpoint) > 1000:
        return HttpResponseBadRequest("Endpoint non valido")
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        "user": request.user, "p256dh": p256dh[:200], "auth": auth[:100], "user_agent": user_agent,
        "label": (data.get("label") or _device_label(user_agent))[:120], "active": True, "failure_count": 0,
    })
    return JsonResponse({"ok": True})


@require_POST
def push_unsubscribe(request):
    if request.content_type == "application/json":
        try:
            endpoint = json.loads(request.body).get("endpoint", "")
        except ValueError:
            return HttpResponseBadRequest("Richiesta non valida")
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return JsonResponse({"ok": True})
    PushSubscription.objects.filter(user=request.user, pk=request.POST.get("pk")).delete()
    messages.success(request, "Dispositivo rimosso: non riceverà più notifiche.")
    return redirect("notifications:devices")


def _test_message(subscription, delivery):
    device, service = subscription.label or "Dispositivo", push.service_name(subscription.endpoint)
    status = f" ({delivery.status})" if delivery.status else ""
    detail = f" Risposta: «{delivery.detail}»." if delivery.detail and delivery.outcome == "rejected" else ""
    return {
        "sent": f"{device}: prova accettata dal servizio push di {service}. Deve comparire entro pochi secondi; "
                "se non compare, il blocco è nel browser o nel sistema operativo di quel dispositivo "
                "(vedi «Non compare nulla?» qui sotto).",
        "gone": f"{device}: l'iscrizione non è più valida{status} (notifiche disattivate o dati del browser "
                "cancellati). Il dispositivo è stato rimosso: riattiva le notifiche da quel dispositivo.",
        "rejected": f"{device}: prova rifiutata dal servizio push di {service}{status}.{detail} Se la chiave del "
                    "server è cambiata dopo l'attivazione, disattiva e riattiva le notifiche su quel dispositivo.",
        "unreachable": f"{device}: il server FASAS non riesce a contattare il servizio push di {service}. "
                       "Controllare la connessione a Internet del computer su cui gira il FASAS (proxy, firewall).",
        "disabled": "Le notifiche push non sono configurate sul server.",
    }.get(delivery.outcome, f"{device}: errore interno durante l'invio (dettagli nel registro del server).")


@require_POST
def push_test(request):
    results = push.send_test(request.user)
    if not results:
        messages.error(request, "Nessun dispositivo attivo: attiva le notifiche dal dispositivo su cui vuoi riceverle.")
    for subscription, delivery in results:
        (messages.success if delivery.ok else messages.error)(request, _test_message(subscription, delivery))
    return redirect("notifications:devices")
