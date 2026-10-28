from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "fasas.core"
    verbose_name = "Sistema"

    def ready(self):
        from django.db.models.signals import post_migrate

        from fasas.audit.services import register

        from .models import Community, SystemConfig
        from .supabase import post_migrate_setup

        register(Community, guest_field=None)
        register(SystemConfig, guest_field=None)
        post_migrate.connect(post_migrate_setup, dispatch_uid="fasas-post-migrate-setup")
