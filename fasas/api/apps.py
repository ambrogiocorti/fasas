from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "fasas.api"
    verbose_name = "API"

    def ready(self):
        from django.contrib.auth import get_user_model
        from django.db.models.signals import pre_save

        pre_save.connect(revoke_on_credentials_change, sender=get_user_model(), dispatch_uid="fasas-api-token-revoke")


def revoke_on_credentials_change(sender, instance, **kwargs):
    """Cambio password o utente disattivato: i token dell'app smettono subito di valere."""
    if instance.pk is None:
        return
    old = sender.objects.filter(pk=instance.pk).values("password", "is_active").first()
    if old and (old["password"] != instance.password or (old["is_active"] and not instance.is_active)):
        from .authentication import revoke_tokens

        revoke_tokens(instance)
