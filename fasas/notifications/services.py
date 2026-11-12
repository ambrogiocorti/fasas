import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from .models import (
    DEFAULT_PUSH,
    DEFAULT_ROLES,
    REQUIRED_PERMISSION,
    Notification,
    NotificationKind,
    NotificationSetting,
)

logger = logging.getLogger("fasas.notifications")

LEVEL_FOR_KIND = {
    NotificationKind.EMERGENCY: Notification.Level.CRITICAL,
    NotificationKind.CRITICAL_EVENT: Notification.Level.CRITICAL,
    NotificationKind.AUDIT_BROKEN: Notification.Level.CRITICAL,
    NotificationKind.PROTOCOL: Notification.Level.WARNING,
}


def setting_for(kind):
    setting = NotificationSetting.objects.filter(kind=kind).first()
    if setting is None:
        setting = NotificationSetting(kind=kind, enabled=True, roles=list(DEFAULT_ROLES.get(kind, ["admin"])),
                                      send_push=kind in DEFAULT_PUSH)
    return setting


def recipients_for(setting, roles=None):
    from fasas.accounts.models import User

    return list(User.objects.filter(is_active=True, role__in=roles or setting.roles))


def notify(kind, title, message="", *, link="", guest=None, level=None, dedup_key="", roles=None, users=None):
    """
    Crea una notifica per ciascun destinatario secondo la configurazione del tipo.
    dedup_key evita di ripetere la stessa notifica (es. un farmaco in scadenza ogni ora).
    """
    setting = setting_for(kind)
    if not setting.enabled:
        return []
    targets = {u.pk: u for u in recipients_for(setting, roles)}
    for user in users or []:
        targets[user.pk] = user
    required = REQUIRED_PERMISSION.get(kind)
    if required:
        targets = {pk: u for pk, u in targets.items() if u.has_perm(required)}
    level = level or LEVEL_FOR_KIND.get(kind, Notification.Level.INFO)
    created = []
    for user in targets.values():
        if dedup_key and Notification.objects.filter(recipient=user, dedup_key=dedup_key).exists():
            continue
        try:
            with transaction.atomic():
                created.append(Notification.objects.create(
                    recipient=user, kind=kind, level=level, title=title[:200], message=message, link=link,
                    guest=guest, dedup_key=dedup_key[:150],
                ))
        except IntegrityError:
            continue
    if setting.send_push and created:
        from . import push

        transaction.on_commit(lambda: push.dispatch(created))
    if setting.send_email and created:
        emails = [n.recipient.email for n in created if n.recipient.email]
        if emails:
            # Le email non contengono dati sanitari: solo un avviso con il rimando al sistema.
            label = NotificationKind(kind).label if kind in NotificationKind.values else "Notifica"
            transaction.on_commit(lambda: _send_email(label, emails))
    return created


def _send_email(title, emails):
    try:
        send_mail(
            f"[FASAS] {title}",
            "È presente una nuova notifica nel sistema FASAS. Accedi per i dettagli.",
            settings.DEFAULT_FROM_EMAIL, emails, fail_silently=False,
        )
    except Exception:  # l'invio email non deve mai bloccare il lavoro clinico
        logger.exception("Invio email notifica fallito")


def unread_for(user):
    return Notification.objects.filter(recipient=user, read_at__isnull=True)


def ensure_default_settings():
    for kind in NotificationKind.values:
        NotificationSetting.objects.get_or_create(kind=kind, defaults={
            "roles": list(DEFAULT_ROLES.get(kind, ["admin"])), "send_push": kind in DEFAULT_PUSH})
