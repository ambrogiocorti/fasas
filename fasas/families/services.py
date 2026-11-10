import datetime

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import FamilyLink, FamilyMessage, SharedDocument, VisitRequest

MAX_PEOPLE = 6


class FamilyError(Exception):
    pass


def links_for(user):
    """Collegamenti attivi del familiare (ospiti non archiviati)."""
    return (FamilyLink.objects.filter(user=user, active=True).exclude(guest__status="archived")
            .select_related("guest").order_by("guest__last_name"))


def link_for(user, pk):
    """Il collegamento del familiare, oppure 403: un familiare non arriva mai a un ospite non suo."""
    link = links_for(user).filter(pk=pk).first()
    if link is None:
        raise PermissionDenied
    return link


def _notify_family(link, title, path):
    from fasas.notifications.models import NotificationKind
    from fasas.notifications.services import notify

    notify(NotificationKind.FAMILY_UPDATE, title, "Apri l'area familiari del FASAS per i dettagli.",
           link=path, users=[link.user])


def _notify_staff(kind, title, link, path, dedup_key):
    from fasas.notifications.services import notify

    # nessun contenuto del messaggio nella notifica (può arrivare per email o sul telefono)
    notify(kind, title, f"Da {link.user.get_full_name() or link.user.username} ({link.get_relation_display()}).",
           link=path, guest=link.guest, dedup_key=dedup_key)


def send_message(link, user, body, from_family):
    from fasas.notifications.models import NotificationKind

    body = (body or "").strip()
    if not body:
        raise FamilyError("Scrivere il messaggio.")
    if len(body) > 2000:
        raise FamilyError("Il messaggio è troppo lungo (al massimo 2000 caratteri).")
    if not link.active or link.guest.is_archived:
        raise FamilyError("Il collegamento non è più attivo.")
    message = FamilyMessage.objects.create(link=link, author=user, from_family=from_family, body=body)
    if from_family:
        _notify_staff(NotificationKind.FAMILY_MESSAGE, f"Messaggio da un familiare di {link.guest}", link,
                      reverse("families:staff_link", args=[link.pk]), f"family-msg-{message.pk}")
    else:
        _notify_family(link, f"Nuovo messaggio dalla struttura su {link.guest.first_name}",
                       reverse("families:guest", args=[link.pk]))
    return message


def mark_read(link, reader, from_family):
    """Segna come letti i messaggi dell'altra parte."""
    return (link.messages.filter(from_family=from_family, read_at__isnull=True)
            .update(read_at=timezone.now(), read_by=reader))


def request_visit(link, user, day, time, people=1, notes="", now=None):
    from fasas.notifications.models import NotificationKind

    now = now or timezone.now()
    moment = timezone.make_aware(datetime.datetime.combine(day, time))
    if moment <= now:
        raise FamilyError("Scegliere un giorno e un'ora futuri.")
    if day > timezone.localdate(now) + datetime.timedelta(days=90):
        raise FamilyError("Le visite si chiedono al massimo con tre mesi di anticipo.")
    if not 1 <= int(people) <= MAX_PEOPLE:
        raise FamilyError(f"Le persone in visita vanno da 1 a {MAX_PEOPLE}.")
    if link.visits.filter(status__in=[VisitRequest.Status.PENDING, VisitRequest.Status.CONFIRMED],
                          day__gte=timezone.localdate(now)).count() >= 5:
        raise FamilyError("Ci sono già 5 visite in programma: attendere che si svolgano o annullarne una.")
    visit = VisitRequest.objects.create(link=link, day=day, time=time, people=people, notes=notes.strip()[:255])
    _notify_staff(NotificationKind.FAMILY_VISIT, f"Richiesta di visita per {link.guest} il {day:%d/%m} alle {time:%H:%M}",
                  link, reverse("families:staff_home"), f"family-visit-{visit.pk}")
    return visit


@transaction.atomic
def decide_visit(visit, user, confirm, note=""):
    if visit.status != VisitRequest.Status.PENDING:
        raise FamilyError("La richiesta è già stata gestita.")
    if not confirm and not note.strip():
        raise FamilyError("Indicare il motivo e, se possibile, un'alternativa.")
    visit.status = VisitRequest.Status.CONFIRMED if confirm else VisitRequest.Status.DECLINED
    visit.decided_by, visit.decided_at, visit.decision_note = user, timezone.now(), note.strip()[:255]
    visit.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    outcome = "confermata" if confirm else "non possibile"
    _notify_family(visit.link, f"Visita del {visit.day:%d/%m} alle {visit.time:%H:%M}: {outcome}",
                   reverse("families:guest", args=[visit.link_id]))
    return visit


def cancel_visit(visit, user):
    if visit.link.user_id != user.pk:
        raise PermissionDenied
    if visit.status not in (VisitRequest.Status.PENDING, VisitRequest.Status.CONFIRMED):
        raise FamilyError("La visita non è più in programma.")
    visit.status = VisitRequest.Status.CANCELLED
    visit.save(update_fields=["status"])
    return visit


def shared_documents(link):
    if not link.can_see_documents:
        return []
    shares = (SharedDocument.objects.filter(document__guest=link.guest, revoked_at__isnull=True)
              .select_related("document").prefetch_related("document__versions"))
    return [s for s in shares if s.document.current_version is not None]


@transaction.atomic
def share_document(document, user, note=""):
    if SharedDocument.objects.filter(document=document, revoked_at__isnull=True).exists():
        raise FamilyError("Il documento è già condiviso.")
    if document.guest.is_archived:
        raise FamilyError("La cartella dell'ospite è archiviata.")
    share = SharedDocument.objects.create(document=document, shared_by=user, note=note.strip()[:255])
    for link in FamilyLink.objects.filter(guest=document.guest, active=True, can_see_documents=True):
        _notify_family(link, f"Nuovo documento condiviso: {document.title}", reverse("families:guest", args=[link.pk]))
    return share


def unshare_document(share, user):
    share.revoked_at, share.revoked_by = timezone.now(), user
    share.save(update_fields=["revoked_at", "revoked_by"])
    return share


def revoke_link(link, user, reason):
    if not reason.strip():
        raise FamilyError("Indicare il motivo della revoca.")
    link.active, link.revoked_at, link.revoked_by = False, timezone.now(), user
    link.revoke_reason = reason.strip()[:255]
    link.save(update_fields=["active", "revoked_at", "revoked_by", "revoke_reason", "updated_at"])
    return link


def unread_for_staff():
    return FamilyMessage.objects.filter(from_family=True, read_at__isnull=True, link__active=True).count()


def pending_visits():
    return VisitRequest.objects.filter(status=VisitRequest.Status.PENDING, day__gte=timezone.localdate()).count()
