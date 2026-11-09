from django.conf import settings
from django.utils import timezone

from .menu import build_menu, role_of
from .shifts import Shift, resolve_shift


def presentation_info():
    """Versione di presentazione online: utenti di prova e, se è quella pubblica, la password da mostrare."""
    if not settings.FASAS_PRESENTAZIONE:
        return None
    from .management.commands.fasas_demo import DEMO_PASSWORD, USERS, demo_password

    return {"users": [user[0] for user in USERS],
            "password": DEMO_PASSWORD if demo_password() == DEMO_PASSWORD else ""}


def fasas(request):
    flags = {
        "dev_keys_in_use": settings.FASAS_DEV_KEYS_IN_USE,  # installazione di prova: chiavi pubbliche
        "presentazione": presentation_info(),
        "cie_enabled": settings.FASAS_CIE_ENABLED,
        "remote_signature_enabled": bool(settings.FASAS_CSC_SERVICE_URL),
    }
    if flags["remote_signature_enabled"] and getattr(request, "fasas_config", None) is not None:
        from .modules import is_on

        flags["remote_signature_enabled"] = is_on("remote_signature", request.fasas_config)
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return flags
    from fasas.notifications.services import unread_for

    config = request.fasas_config
    day, shift = resolve_shift(config=config)
    theme = request.user.theme
    if theme == "auto":
        theme = "dark" if (shift == Shift.NIGHT and config.night_theme_auto) else "light"
    unread = unread_for(request.user).count()
    from .modules import states

    return {
        **flags,
        "modules": states(config),
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
