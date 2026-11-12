from django.core.management.base import CommandError

from fasas.accounts.models import User


def get_user(username):
    try:
        return User.objects.get(username=username, is_active=True)
    except User.DoesNotExist:
        raise CommandError(f"Utente «{username}» non trovato o disattivato.") from None
