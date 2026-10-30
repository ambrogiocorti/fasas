"""
Notifiche push (Web Push con chiavi VAPID) sui telefoni e tablet degli operatori.

Il contenuto è cifrato end-to-end tra il server FASAS e il browser (RFC 8291): il servizio push del
produttore (Google, Mozilla, Apple) non lo può leggere. Per default il testo non contiene comunque
dati sanitari né nomi, perché compare sulla schermata di blocco: solo il tipo di avviso e un collegamento.
Con FASAS_PUSH_SHOW_DETAILS=1 si mostrano titolo e messaggio completi (solo per dispositivi personali protetti).
"""
import base64
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.db import close_old_connections
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger("fasas.push")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fasas-push")
_SECP256R1_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
MAX_FAILURES = 5

try:  # pywebpush è opzionale: senza, le notifiche restano solo nell'applicazione
    from pywebpush import WebPushException, webpush
    from requests import RequestException
except ImportError:  # pragma: no cover
    webpush = None
    WebPushException = RequestException = Exception

# Servizio push del produttore del browser, riconosciuto dall'endpoint dell'iscrizione.
PUSH_SERVICES = [
    ("fcm.googleapis.com", "Google (Chrome)"), ("notify.windows.com", "Microsoft (Edge)"),
    ("push.services.mozilla.com", "Mozilla (Firefox)"), ("push.apple.com", "Apple (Safari)"),
]


def service_name(endpoint):
    host = urlparse(endpoint).hostname or ""
    return next((name for key, name in PUSH_SERVICES if host == key or host.endswith("." + key)), host or "?")


def endpoint_hash(endpoint):
    """Impronta dell'endpoint: la pagina dei dispositivi la confronta con quella del browser senza esporre l'URL."""
    return hashlib.sha256(endpoint.encode()).hexdigest()


@dataclass
class Delivery:
    """Esito di un invio: ok se il servizio push l'ha accettato (consegna al dispositivo a cura del browser)."""

    ok: bool
    outcome: str  # sent, gone, rejected, unreachable, error, disabled
    status: int | None = None
    detail: str = ""


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def load_private_key(value):
    value = (value or "").strip()
    if value.startswith("-----BEGIN"):
        return serialization.load_pem_private_key(value.encode(), password=None)
    raw = _b64url_decode(value)
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def generate_private_key():
    key = ec.generate_private_key(ec.SECP256R1())
    return _b64url(key.private_numbers().private_value.to_bytes(32, "big"))


def private_key():
    """Chiave VAPID: da FASAS_VAPID_PRIVATE_KEY; in sviluppo derivata (stabile) da SECRET_KEY."""
    if settings.FASAS_VAPID_PRIVATE_KEY:
        return load_private_key(settings.FASAS_VAPID_PRIVATE_KEY)
    if settings.DEBUG:
        seed = int.from_bytes(hashlib.sha256(b"fasas-vapid:" + settings.SECRET_KEY.encode()).digest(), "big")
        return ec.derive_private_key(seed % (_SECP256R1_ORDER - 1) + 1, ec.SECP256R1())
    return None


def public_key():
    key = private_key()
    if key is None:
        return ""
    return _b64url(key.public_key().public_bytes(serialization.Encoding.X962,
                                                 serialization.PublicFormat.UncompressedPoint))


def is_enabled():
    return webpush is not None and private_key() is not None


def payload_for(notification):
    if settings.FASAS_PUSH_SHOW_DETAILS:
        title, body = notification.title, notification.message[:180]
    else:
        title = f"FASAS · {notification.get_kind_display()}"
        body = "Apri FASAS per i dettagli."
    return {
        "title": title, "body": body, "level": notification.level, "tag": f"fasas-{notification.kind}",
        "url": reverse("notifications:open", args=[notification.pk]),
    }


def _send(subscription, payload, urgent=False):
    from .models import PushSubscription

    key = private_key()
    if webpush is None or key is None:
        return Delivery(False, "disabled")
    from py_vapid import Vapid02

    try:
        webpush(
            subscription_info={"endpoint": subscription.endpoint,
                               "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps(payload), vapid_private_key=Vapid02(private_key=key),
            vapid_claims={"sub": settings.FASAS_VAPID_SUBJECT}, ttl=6 * 3600 if urgent else 3600,
            headers={"Urgency": "high" if urgent else "normal"}, timeout=10,
        )
    except WebPushException as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        # Il testo d'errore del servizio push non contiene il messaggio (cifrato): serve a capire il rifiuto.
        detail = " ".join(str(getattr(response, "text", "") or "").split())[:200]
        if status in (404, 410):  # iscrizione scaduta o revocata dal browser
            PushSubscription.objects.filter(pk=subscription.pk).delete()
            return Delivery(False, "gone", status, detail)
        PushSubscription.objects.filter(pk=subscription.pk).update(failure_count=F("failure_count") + 1)
        PushSubscription.objects.filter(pk=subscription.pk, failure_count__gte=MAX_FAILURES).delete()
        logger.warning("Invio push rifiutato da %s (%s) per l'iscrizione %s: %s",
                       service_name(subscription.endpoint), status, subscription.pk, detail)
        return Delivery(False, "rejected", status, detail)
    except RequestException as exc:  # il server FASAS non raggiunge il servizio push (rete, proxy, firewall)
        logger.warning("Servizio push %s non raggiungibile per l'iscrizione %s: %s",
                       service_name(subscription.endpoint), subscription.pk, type(exc).__name__)
        return Delivery(False, "unreachable", detail=type(exc).__name__)
    except Exception:  # la rete del server non deve mai bloccare il lavoro clinico
        logger.exception("Invio push fallito per l'iscrizione %s", subscription.pk)
        return Delivery(False, "error")
    PushSubscription.objects.filter(pk=subscription.pk).update(last_success_at=timezone.now(), failure_count=0)
    return Delivery(True, "sent", 201)


def _deliver(notification_ids):
    from .models import Notification, PushSubscription

    try:
        notifications = Notification.objects.filter(pk__in=notification_ids)
        for notification in notifications:
            payload = payload_for(notification)
            urgent = notification.level == Notification.Level.CRITICAL
            for subscription in PushSubscription.objects.filter(user_id=notification.recipient_id, active=True):
                _send(subscription, payload, urgent)
    finally:
        if settings.FASAS_PUSH_ASYNC:
            close_old_connections()


def dispatch(notifications):
    """Chiamata a transazione conclusa: l'invio avviene in background per non rallentare la registrazione."""
    ids = [n.pk for n in notifications]
    if not ids or not is_enabled():
        return
    if settings.FASAS_PUSH_ASYNC:
        _executor.submit(_deliver, ids)
    else:
        _deliver(ids)


def send_test(user):
    """Invia la prova a ogni dispositivo dell'utente: elenco di (iscrizione, esito)."""
    from .models import PushSubscription

    payload = {"title": "FASAS · Prova", "body": "Le notifiche su questo dispositivo funzionano.",
               "level": "info", "tag": "fasas-test", "url": reverse("notifications:devices")}
    return [(s, _send(s, payload)) for s in PushSubscription.objects.filter(user=user, active=True)]
