from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "fasas.accounts"
    verbose_name = "Utenti e accessi"

    def ready(self):
        from django.contrib.auth import signals

        from fasas.audit.services import register

        from . import receivers
        from .models import User, UserPermissionOverride

        register(User, exclude={"last_login"}, redact={"password"}, guest_field=None)
        register(UserPermissionOverride, guest_field=None)
        signals.user_logged_in.connect(receivers.on_login, dispatch_uid="fasas-login")
        signals.user_logged_out.connect(receivers.on_logout, dispatch_uid="fasas-logout")
        signals.user_login_failed.connect(receivers.on_login_failed, dispatch_uid="fasas-login-failed")
