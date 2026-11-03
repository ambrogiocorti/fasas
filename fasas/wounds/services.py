import datetime
from io import BytesIO

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from fasas.core.locking import creation_decision
from fasas.core.models import SystemConfig

from .models import Dressing, DressingPlan, Wound, WoundCheck

PHOTO_MAX_SIDE = 2000


class WoundError(Exception):
    pass


def _check_new_record(guest, occurred_at, user):
    occurred_at = occurred_at or timezone.now()
    if occurred_at > timezone.now() + datetime.timedelta(minutes=10):
        raise WoundError("La data indicata è nel futuro.")
    decision = creation_decision(guest, occurred_at, user)
    if not decision.allowed:
        raise WoundError(decision.message)
    return occurred_at


def _ensure_open(wound):
    if not wound.is_open:
        raise WoundError("La lesione è chiusa: per una nuova lesione nella stessa sede registrarne una nuova.")


def clean_photo(uploaded):
    """
    Foto della lesione: solo immagini vere (JPEG o PNG), raddrizzate, ridotte a 2000 pixel e salvate senza i dati
    EXIF (posizione GPS, modello del telefono). Restituisce i byte JPEG da cifrare.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError  # dipendenza di reportlab

    limit = SystemConfig.get().max_upload_mb * 1024 * 1024
    if uploaded.size > limit:
        raise WoundError(f"La foto supera la dimensione massima di {SystemConfig.get().max_upload_mb} MB.")
    try:
        image = Image.open(uploaded)
        if image.format not in ("JPEG", "PNG"):
            raise WoundError("Formato non ammesso: usare una foto JPEG o PNG.")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
        output = BytesIO()
        image.convert("RGB").save(output, "JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise WoundError("Il file non è un'immagine leggibile.") from None
    return output.getvalue()


@transaction.atomic
def create_wound(guest, user, *, occurred_at=None, notify_team=True, **fields):
    occurred_at = _check_new_record(guest, occurred_at, user)
    if fields.get("kind") != Wound.Kind.PRESSURE:
        fields["stage"] = ""
    wound = Wound.objects.create(guest=guest, occurred_at=occurred_at, **fields)
    if notify_team:
        from fasas.notifications.services import notify

        notify("wound_new", f"Nuova lesione: {guest}",
               f"{wound} – {wound.get_origin_display().lower()}"
               + (f", {wound.get_stage_display().lower()}" if wound.stage else "") + ".",
               link=wound.get_absolute_url(), guest=guest, dedup_key=f"wound-new-{wound.pk}")
    return wound


@transaction.atomic
def add_check(wound, user, *, occurred_at=None, photo=None, **fields):
    _ensure_open(wound)
    occurred_at = _check_new_record(wound.guest, occurred_at, user)
    if wound.kind != Wound.Kind.PRESSURE:
        fields["stage"] = ""
    document = None
    if photo is not None:
        from fasas.documents.models import Document
        from fasas.documents.services import create_document

        data = clean_photo(photo)
        when = timezone.localtime(occurred_at)
        document = create_document(
            wound.guest, Document.Category.WOUND_PHOTO, f"Foto {wound} – {when:%d/%m/%Y}", user=user, data=data,
            filename=f"lesione-{wound.pk}-{when:%Y%m%d-%H%M}.jpg", document_date=when.date())
    return WoundCheck.objects.create(guest=wound.guest, wound=wound, occurred_at=occurred_at, photo=document,
                                     **fields)


@transaction.atomic
def set_plan(wound, user, *, products, procedure="", interval_days, start_date=None, indicated_by):
    """Nuova indicazione di medicazione: quella in corso termina oggi."""
    _ensure_open(wound)
    if wound.guest.is_archived:
        raise WoundError("La cartella dell'ospite è archiviata: non è possibile inserire dati.")
    if not 1 <= interval_days <= 60:
        raise WoundError("La frequenza deve essere tra 1 e 60 giorni.")
    today = timezone.localdate()
    Wound.objects.select_for_update().get(pk=wound.pk)
    for plan in wound.plans.filter(active=True):
        plan.active = False
        plan.ended_on = today
        plan.save(update_fields=["active", "ended_on", "updated_at"])
    return DressingPlan.objects.create(wound=wound, products=products, procedure=procedure,
                                       interval_days=interval_days, start_date=start_date or today,
                                       indicated_by=indicated_by)


def register_dressing(wound, user, *, occurred_at=None, products_used="", notes=""):
    _ensure_open(wound)
    occurred_at = _check_new_record(wound.guest, occurred_at, user)
    return Dressing.objects.create(guest=wound.guest, wound=wound, plan=wound.active_plan, occurred_at=occurred_at,
                                   products_used=products_used, notes=notes)


@transaction.atomic
def close_wound(wound, user, status, note="", closed_at=None):
    _ensure_open(wound)
    if status not in (Wound.Status.HEALED, Wound.Status.CLOSED):
        raise WoundError("Esito di chiusura non previsto.")
    closed_at = closed_at or timezone.now()
    if closed_at > timezone.now() + datetime.timedelta(minutes=10):
        raise WoundError("La data indicata è nel futuro.")
    if closed_at < wound.occurred_at:
        raise WoundError("La chiusura precede la prima osservazione della lesione.")
    if status == Wound.Status.CLOSED and not note.strip():
        raise WoundError("Indicare il motivo della chiusura (es. dimissione, trasferimento).")
    wound.status, wound.closed_at, wound.closed_by, wound.close_note = status, closed_at, user, note
    wound.save(update_fields=["status", "closed_at", "closed_by", "close_note", "updated_at"])
    for plan in wound.plans.filter(active=True):
        plan.active = False
        plan.ended_on = timezone.localtime(closed_at).date()
        plan.save(update_fields=["active", "ended_on", "updated_at"])
    return wound


def _open_wounds(guests=None):
    from fasas.guests.models import Guest

    wounds = Wound.objects.filter(status=Wound.Status.OPEN).exclude(guest__status=Guest.Status.ARCHIVED)
    if guests is not None:
        wounds = wounds.filter(guest__in=guests)
    return wounds.select_related("guest").prefetch_related("plans", "dressings", "checks")


def _last(records):
    valid = [r for r in records if r.voided_at is None]
    return max(valid, key=lambda r: r.occurred_at) if valid else None


def due_list(today=None, guests=None):
    """
    Medicazioni e rivalutazioni da fare: medicazione dovuta oggi o prima secondo il piano in corso,
    rivalutazione (misure e foto) dovuta secondo la frequenza della lesione.
    """
    today = today or timezone.localdate()
    rows = []
    for wound in _open_wounds(guests):
        plans = [p for p in wound.plans.all() if p.active]
        plan = max(plans, key=lambda p: (p.start_date, p.pk)) if plans else None
        if plan is not None:
            last = _last(list(wound.dressings.all()))
            due = plan.start_date
            if last is not None:
                due = max(due, timezone.localtime(last.occurred_at).date() + datetime.timedelta(days=plan.interval_days))
            if due <= today:
                rows.append({"wound": wound, "guest": wound.guest, "what": "dressing", "label": "Medicazione",
                             "plan": plan, "last": last, "due": due, "overdue": due < today})
        if wound.check_interval_days:
            last_check = _last(list(wound.checks.all()))
            base = timezone.localtime(last_check.occurred_at if last_check else wound.occurred_at).date()
            due = base + datetime.timedelta(days=wound.check_interval_days)
            if due <= today:
                rows.append({"wound": wound, "guest": wound.guest, "what": "check", "label": "Rivalutazione",
                             "plan": plan, "last": last_check, "due": due, "overdue": due < today})
    return sorted(rows, key=lambda r: (r["due"], r["guest"].last_name, r["what"]))


def due_reminders(today=None):
    """Job: avvisa il coordinatore delle medicazioni e rivalutazioni scadute (una volta per scadenza)."""
    from fasas.notifications.services import notify

    today = today or timezone.localdate()
    sent = 0
    for row in due_list(today):
        if not row["overdue"]:
            continue
        wound = row["wound"]
        notify("dressing_due", f"{row['label']} in ritardo: {row['guest']}",
               f"{wound}: {row['label'].lower()} prevista il {row['due']:%d/%m/%Y}.",
               link=reverse("wounds:detail", args=[wound.pk]), guest=row["guest"],
               dedup_key=f"wound-{wound.pk}-{row['what']}-{row['due']}")
        sent += 1
    return {"overdue": sent}
