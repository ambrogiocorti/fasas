from django.utils import timezone

from .menu import build_menu, role_of
from .shifts import Shift, resolve_shift


def fasas(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from fasas.notifications.services import unread_for

    config = request.fasas_config
    day, shift = resolve_shift(config=config)
    theme = request.user.theme
    if theme == "auto":
        theme = "dark" if (shift == Shift.NIGHT and config.night_theme_auto) else "light"
    unread = unread_for(request.user).count()
    return {
        "current_shift": {"day": day, "code": shift, "label": Shift(shift).label},
        "community": config.community,
        "fasas_config": config,
        "unread_notifications": unread,
        "menu": build_menu(request, unread),
        "user_role": role_of(request.user),
        "ui_theme": theme,
        "user_theme_pref": request.user.theme,
        "now": timezone.localtime(),
    }
