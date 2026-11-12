from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import read_encrypted, sha256, store_encrypted
from fasas.core.uploads import UploadError, clean_pdf_or_photo

from . import defaults, pdf
from .models import FormAssignment, FormField, FormSettings, FormSubmission, FormTemplate
from .text import substitute


class FormError(Exception):
    pass


# --- Moduli predefiniti ---------------------------------------------------------------------------------------


def _apply_default(template, data):
    for attr in ("title", "intro", "for_guests", "for_family", "for_staff", "staff_roles", "auto_assign",
                 "requires_signature", "withdrawable", "signatures", "document_category"):
        default = {"staff_roles": [], "signatures": [], "document_category": "form"}.get(attr, False)
        setattr(template, attr, data.get(attr, default if attr not in ("title", "intro") else ""))
    template.save()
    template.fields.all().delete()
    FormField.objects.bulk_create([
        FormField(template=template, key=key, label=label, kind=kind, required=required, options=list(options),
                  help_text=help_text, order=i * 10)
        for i, (key, label, kind, required, options, help_text) in enumerate(data.get("fields", []))])


def ensure_defaults():
    """Crea i moduli predefiniti che mancano (non tocca quelli già presenti, anche se modificati)."""
    created = 0
    for order, data in enumerate(defaults.TEMPLATES):
        if FormTemplate.objects.filter(code=data["code"]).exists():
            continue
        template = FormTemplate(code=data["code"], status=FormTemplate.Status.PUBLISHED, order=order * 10,
                                published_at=timezone.now())
        _apply_default(template, data)
        created += 1
    return created


def default_for(code):
    return next((d for d in defaults.TEMPLATES if d["code"] == code), None)


@transaction.atomic
def restore_default(template, user):
    data = default_for(template.code)
    if data is None:
        raise FormError("Questo modulo non ha un testo predefinito.")
    bump_version(template)
    template.updated_by = user
    _apply_default(template, data)
    return template


def bump_version(template):
    """Una nuova versione se la versione attuale è già stata compilata (le compilazioni restano com'erano)."""
    if template.submissions.filter(version=template.version).exists():
        template.version += 1


# --- Testo e fotografia del modulo ----------------------------------------------------------------------------


def variables(guest=None, user=None, settings_obj=None):
    values = (settings_obj or FormSettings.get()).variables()
    if guest is not None:
        values["ospite"] = f"{guest.first_name} {guest.last_name}"
    if user is not None:
        values["utente"] = user.get_full_name() or user.username
        values["ruolo"] = user.get_role_display().lower() if hasattr(user, "get_role_display") else ""
    return values


def snapshot(template, guest=None, user=None, settings_obj=None):
    settings_obj = settings_obj or FormSettings.get()
    values = variables(guest, user, settings_obj)
    return {
        "code": template.code, "title": substitute(template.title, values), "version": template.version,
        "intro": substitute(template.intro, values), "requires_signature": template.requires_signature,
        "signatures": [substitute(s, values) for s in template.signatures],
        "fields": [{"key": f.key, "label": substitute(f.label, values), "kind": f.kind, "required": f.required,
                    "options": f.options, "help_text": f.help_text} for f in template.fields.all()],
        "header": {"holder": settings_obj.holder, "address": settings_obj.address, "contacts": settings_obj.contacts,
                   "struttura": settings_obj.community.name},
        "subject_label": ("" if guest is not None or user is not None else "Ospite" if template.for_guests
                          else "Dipendente" if template.for_staff else ""),
    }


def blank_pdf(template):
    return pdf.render(snapshot(template))


def display_answers(snap, answers):
    """Risposte leggibili, nell'ordine dei campi (per le pagine e per il PDF)."""
    rows = []
    for field in snap.get("fields", []):
        if field["kind"] == "section":
            continue
        value = answers.get(field["key"])
        if field["kind"] == "check":
            value = "sì" if value else "no"
        elif isinstance(value, list):
            value = ", ".join(value)
        rows.append((field["label"], value or "—"))
    return rows


# --- Compilazione ----------------------------------------------------------------------------------------------


def _record(submission):
    when = timezone.localtime(submission.created_at)
    who = submission.respondent or (submission.created_by.get_full_name() or submission.created_by.username)
    role = f" ({submission.respondent_role})" if submission.respondent_role else ""
    operator = submission.created_by.get_full_name() or submission.created_by.username
    ip = f", indirizzo IP {submission.ip_address}" if submission.ip_address else ""
    text = (f"Compilato online il {when:%d/%m/%Y} alle {when:%H:%M} da {who}{role}; registrazione effettuata con "
            f"l'utente FASAS di {operator}{ip}. La conferma online documenta chi ha risposto e quando")
    if submission.snapshot.get("requires_signature"):
        return text + ": il modulo va comunque firmato qui sotto."
    return text + "."


def _subject(submission):
    if submission.guest_id:
        return f"Ospite: {submission.guest.first_name} {submission.guest.last_name}"
    if submission.subject_user_id:
        user = submission.subject_user
        return f"Dipendente: {user.get_full_name() or user.username} ({user.get_role_display()})"
    return ""


def submission_pdf_bytes(submission):
    return pdf.render(submission.snapshot, submission.answers,
                      {"subject": _subject(submission), "record": _record(submission)})


@transaction.atomic
def submit(template, answers, user, *, guest=None, family_link=None, subject_user=None, respondent="",
           respondent_role="", ip=None, assignment=None):
    from fasas.notifications.models import NotificationKind
    from fasas.notifications.services import notify

    if not template.is_published:
        raise FormError("Il modulo non è pubblicato.")
    if guest is not None and guest.is_archived:
        raise FormError("La cartella dell'ospite è archiviata.")
    snap = snapshot(template, guest=guest, user=subject_user)
    submission = FormSubmission.objects.create(
        template=template, version=template.version, snapshot=snap, answers=answers, guest=guest,
        family_link=family_link, subject_user=subject_user, respondent=respondent.strip()[:200],
        respondent_role=respondent_role[:100], created_by=user, ip_address=ip)
    data = submission_pdf_bytes(submission)
    submission.pdf_storage = store_encrypted(data, "moduli")
    submission.pdf_sha256 = sha256(data)
    if guest is not None:
        from fasas.documents.services import create_document

        submission.document = create_document(
            guest, template.document_category or "form", f"{snap['title']} ({timezone.localdate():%d/%m/%Y})",
            user=user, data=data, filename=f"{template.code}.pdf",
            description="Modulo compilato con la modulistica del FASAS")
    submission.save()
    if assignment is not None:
        assignment.submission = submission
        assignment.save(update_fields=["submission"])
    if family_link is not None:
        notify(NotificationKind.FORM_RECEIVED, f"Modulo compilato da un familiare: {snap['title']}",
               f"Ospite: {guest}.", link=reverse("modulistica:guest", args=[guest.pk]), guest=guest,
               dedup_key=f"form-{submission.pk}")
    return submission


def read_pdf(submission, user, signed=False):
    storage, digest = ((submission.signed_storage, submission.signed_sha256) if signed
                       else (submission.pdf_storage, submission.pdf_sha256))
    data = read_encrypted(storage)
    if sha256(data) != digest:
        raise FormError("Il file non corrisponde all'impronta registrata: possibile alterazione.")
    log_event(AuditLog.Action.DOWNLOAD, submission, user=user, guest=submission.guest)
    return data


@transaction.atomic
def attach_signed(submission, uploaded, user):
    """Scansione (o foto) del modulo firmato a mano: completa il modulo e, per gli ospiti, entra nel fascicolo."""
    if submission.withdrawn_at:
        raise FormError("Il modulo è stato revocato.")
    try:
        data, content_type = clean_pdf_or_photo(uploaded)
    except UploadError as exc:
        raise FormError(str(exc)) from None
    submission.signed_storage = store_encrypted(data, "moduli")
    submission.signed_sha256, submission.signed_type = sha256(data), content_type
    submission.signed_at, submission.signed_by = timezone.now(), user
    submission.save(update_fields=["signed_storage", "signed_sha256", "signed_type", "signed_at", "signed_by"])
    if submission.document_id:
        from fasas.documents.services import add_version

        extension = "pdf" if content_type == "application/pdf" else "jpg"
        add_version(submission.document, data, f"{submission.template.code}-firmato.{extension}", user,
                    note="Scansione del modulo firmato a mano", content_type=content_type)
    return submission


def withdraw(submission, user, reason):
    if not submission.snapshot or not submission.template.withdrawable:
        raise FormError("Questo modulo non si revoca: se serve, se ne compila uno nuovo.")
    if submission.withdrawn_at:
        raise FormError("Già revocato.")
    if not reason.strip():
        raise FormError("Indicare il motivo o chi ha chiesto la revoca.")
    submission.withdrawn_at, submission.withdrawn_by = timezone.now(), user
    submission.withdraw_reason = reason.strip()[:255]
    submission.save(update_fields=["withdrawn_at", "withdrawn_by", "withdraw_reason"])
    return submission


# --- Distribuzione al personale ----------------------------------------------------------------------------------


def _assign(template, user, by=None, due_date=None, notify_user=True):
    from fasas.notifications.models import NotificationKind
    from fasas.notifications.services import notify

    if FormAssignment.objects.filter(template=template, user=user, version=template.version, cancelled=False).exists():
        return None
    assignment = FormAssignment.objects.create(template=template, user=user, version=template.version,
                                               assigned_by=by, due_date=due_date)
    if not notify_user:  # nuovo utente: lo vede nel contatore «I miei moduli» al primo accesso
        return assignment
    due = f" entro il {due_date:%d/%m/%Y}" if due_date else ""
    notify(NotificationKind.FORM_TO_FILL, f"Modulo da compilare: {template.title}",
           f"Lo trovi in «I miei moduli»{due}.", link=reverse("modulistica:mine"), users=[user],
           dedup_key=f"form-assign-{assignment.pk}")
    return assignment


@transaction.atomic
def distribute(template, roles, by, due_date=None):
    from fasas.accounts.models import User

    if not template.is_published or not template.for_staff:
        raise FormError("Si distribuiscono al personale solo i moduli pubblicati e destinati al personale.")
    if not roles:
        raise FormError("Scegliere almeno un ruolo.")
    from fasas.notifications.models import NotificationKind
    from fasas.notifications.services import notify

    count = 0
    for user in User.objects.filter(is_active=True, role__in=roles):
        if _assign(template, user, by, due_date):
            count += 1
            continue
        # già assegnato e non ancora compilato: la distribuzione vale come promemoria (una volta al giorno)
        pending = FormAssignment.objects.filter(template=template, user=user, version=template.version,
                                                cancelled=False, submission__isnull=True).first()
        if pending is not None:
            if due_date and pending.due_date != due_date:
                pending.due_date = due_date
                pending.save(update_fields=["due_date"])
            notify(NotificationKind.FORM_TO_FILL, f"Promemoria: modulo da compilare – {template.title}",
                   "Lo trovi in «I miei moduli».", link=reverse("modulistica:mine"), users=[user],
                   dedup_key=f"form-remind-{pending.pk}-{timezone.localdate():%Y%m%d}")
            count += 1
    return count


def assign_new_user(sender, instance, created, **kwargs):
    """Nuovo utente: riceve i moduli del personale contrassegnati «chiedere anche ai nuovi utenti»."""
    if not created or not instance.is_active or instance.role == "family":
        return
    for template in FormTemplate.objects.filter(status=FormTemplate.Status.PUBLISHED, for_staff=True, auto_assign=True):
        if instance.role in (template.staff_roles or []):
            _assign(template, instance, notify_user=False)


def pending_for(user):
    return (FormAssignment.objects.filter(user=user, submission__isnull=True, cancelled=False,
                                          template__status=FormTemplate.Status.PUBLISHED)
            .select_related("template"))


def staff_status(template):
    """Per l'amministratore: chi del personale ha compilato la versione corrente e chi no."""
    assignments = (FormAssignment.objects.filter(template=template, cancelled=False)
                   .select_related("user", "submission").order_by("user__last_name"))
    latest = {}
    for a in assignments:
        if a.user_id not in latest or a.version > latest[a.user_id].version:
            latest[a.user_id] = a
    return list(latest.values())

