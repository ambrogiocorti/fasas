from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from fasas.accounts.models import Role

from .models import Notification, NotificationSetting
from .services import ensure_default_settings, unread_for


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
            setting.roles = [r for r in Role.values if request.POST.get(f"role_{setting.pk}_{r}")]
            setting.save()
        messages.success(request, "Impostazioni notifiche salvate.")
        return redirect("notifications:settings")
    return render(request, "notifications/settings.html", {"settings_list": settings_list, "roles": Role.choices})
