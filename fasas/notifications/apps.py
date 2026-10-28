from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "fasas.notifications"
    verbose_name = "Notifiche"

    def ready(self):
        from fasas.audit.services import register

        from .models import NotificationSetting

        register(NotificationSetting, guest_field=None)
