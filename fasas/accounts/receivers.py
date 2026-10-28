from .models import AccessLog
from .services import record_access


def on_login(sender, request, user, **kwargs):
    record_access(request, AccessLog.Event.LOGIN, user.get_username(), user)


def on_logout(sender, request, user, **kwargs):
    if user is not None:
        event = AccessLog.Event.TIMEOUT if getattr(request, "fasas_session_timeout", False) else AccessLog.Event.LOGOUT
        record_access(request, event, user.get_username(), user)


def on_login_failed(sender, credentials, request=None, **kwargs):
    record_access(request, AccessLog.Event.FAILED, credentials.get("username", ""))
