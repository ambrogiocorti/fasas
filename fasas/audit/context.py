"""Contesto dell'audit: chi sta agendo, da dove e con quale motivazione."""
from contextlib import contextmanager
from contextvars import ContextVar

_user = ContextVar("fasas_audit_user", default=None)
_ip = ContextVar("fasas_audit_ip", default="")
_reason = ContextVar("fasas_audit_reason", default="")
_source = ContextVar("fasas_audit_source", default="web")

_UNSET = object()


def current_user():
    return _user.get()


def current_ip():
    return _ip.get()


def current_reason():
    return _reason.get()


def current_source():
    return _source.get()


def set_current_user(user):
    """Per l'API: l'utente è noto solo dopo l'autenticazione DRF. Il middleware ripristina il valore a fine richiesta."""
    _user.set(user if getattr(user, "is_authenticated", False) else None)


@contextmanager
def audit_context(user=_UNSET, ip=_UNSET, reason=_UNSET, source=_UNSET):
    """Imposta temporaneamente i valori indicati; quelli non indicati restano invariati."""
    tokens = []
    for var, value in ((_user, user), (_ip, ip), (_reason, reason), (_source, source)):
        if value is not _UNSET:
            tokens.append((var, var.set(value)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
