import datetime

from django.db import transaction
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from .models import PAI


class PAIError(Exception):
    pass


def create_first(guest, user, review_due):
    if guest.pais.exists():
        raise PAIError("L'ospite ha già un PAI: crearne una revisione.")
    return PAI.objects.create(guest=guest, version=1, review_due=review_due)


@transaction.atomic
def create_revision(pai, user):
    """Nuova bozza a partire da una versione esistente, con copia degli obiettivi."""
    if pai.guest.is_archived:
        raise PAIError("Cartella archiviata.")
    if pai.guest.pais.filter(status=PAI.Status.DRAFT).exists():
        raise PAIError("Esiste già una bozza di revisione in corso.")
    last_version = pai.guest.pais.order_by("-version").first().version
    revision = PAI.objects.create(
        guest=pai.guest, version=last_version + 1, review_due=pai.review_due, summary=pai.summary,
        participants=pai.participants, previous=pai,
    )
    for goal in pai.goals.all():
        goal.pk = None
        goal.pai = revision
        goal.save()
    return revision


@transaction.atomic
def activate(pai, user):
    if not user.has_perm("pai.approve_pai"):
        raise PAIError("Non hai il permesso di approvare il PAI.")
    if pai.status != PAI.Status.DRAFT:
        raise PAIError("Solo una bozza può essere messa in vigore.")
    if not pai.goals.exists():
        raise PAIError("Il PAI deve contenere almeno un obiettivo.")
    for current in pai.guest.pais.filter(status=PAI.Status.ACTIVE):
        current.status = PAI.Status.SUPERSEDED
        current.save()
    pai.status = PAI.Status.ACTIVE
    pai.valid_from = timezone.localdate()
    pai.approved_by = user
    pai.approved_at = timezone.now()
    pai.save()
    log_event(AuditLog.Action.UPDATE, pai, changes={"stato": ["bozza", "in vigore"]})
    return pai


def archive_pdf(pai, user):
    """Genera il PDF del PAI e lo archivia (cifrato) tra i documenti dell'ospite: si può poi firmare."""
    from fasas.documents.models import Document
    from fasas.documents.services import add_version, create_document
    from fasas.reports.pdf import pai_pdf

    data = pai_pdf(pai)
    filename = f"PAI_v{pai.version}_{pai.guest.last_name}.pdf"
    if pai.document_id:
        add_version(pai.document, data, filename, user, note="Rigenerato", content_type="application/pdf")
    else:
        document = create_document(pai.guest, Document.Category.PAI, f"PAI versione {pai.version}", user=user,
                                   data=data, filename=filename, document_date=pai.valid_from or timezone.localdate())
        pai.document = document
        pai.save(update_fields=["document"])
    return pai.document


def review_reminders(today=None):
    from fasas.core.models import SystemConfig
    from fasas.notifications.services import notify

    today = today or timezone.localdate()
    limit = today + datetime.timedelta(days=SystemConfig.get().pai_review_warning_days)
    sent = 0
    for pai in PAI.objects.filter(status=PAI.Status.ACTIVE, review_due__lte=limit).select_related("guest"):
        overdue = pai.review_due < today
        notify(
            "pai_review",
            f"{'Revisione PAI SCADUTA' if overdue else 'Revisione PAI in scadenza'}: {pai.guest}",
            f"Il PAI v{pai.version} va rivisto entro il {pai.review_due:%d/%m/%Y}.",
            link=pai.get_absolute_url(), guest=pai.guest, level="warning" if overdue else "info",
            dedup_key=f"pai-review-{pai.pk}-{'overdue' if overdue else 'soon'}",
        )
        sent += 1
    for pai in PAI.objects.filter(status=PAI.Status.ACTIVE).prefetch_related("goals"):
        for goal in pai.goals.all():
            if goal.outcome == goal.Outcome.ONGOING and goal.verification_date <= today:
                notify(
                    "pai_review", f"Verifica obiettivo PAI: {pai.guest}",
                    f"{goal.get_area_display()}: {goal.objective[:120]} (verifica prevista il {goal.verification_date:%d/%m/%Y}).",
                    link=pai.get_absolute_url(), guest=pai.guest,
                    users=[goal.responsible] if goal.responsible else None,
                    dedup_key=f"pai-goal-{goal.pk}-{goal.verification_date}",
                )
    return {"reviews": sent}
