"""
Token dell'API con ciclo di vita (report di analisi, P1): scadenza, rotazione a ogni accesso, revoca al cambio
password, alla disattivazione dell'utente, alla reimpostazione della verifica in due passaggi e su richiesta.
"""
import datetime

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed


def token_expired(token, now=None):
    return (now or timezone.now()) - token.created > datetime.timedelta(days=settings.FASAS_API_TOKEN_DAYS)


def issue_token(user):
    """Nuovo token a ogni accesso: quello precedente smette di valere (rotazione)."""
    Token.objects.filter(user=user).delete()
    return Token.objects.create(user=user)


def revoke_tokens(user):
    return Token.objects.filter(user=user).delete()[0]


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token_expired(token):
            token.delete()
            raise AuthenticationFailed("Token scaduto: accedere di nuovo per ottenerne uno nuovo.")
        return user, token
