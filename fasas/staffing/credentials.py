"""
Scadenze del personale: corsi (BLSD, antincendio, sicurezza, HACCP…), idoneità alla mansione e visite.
Per ogni dipendente e tipo conta la registrazione più recente; il job giornaliero avvisa il coordinatore,
l'ufficio amministrativo e il dipendente interessato prima della scadenza.
"""
import csv
import datetime
import io
from dataclasses import dataclass

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from fasas.accounts.models import Role, User
from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import read_encrypted, sha256, store_encrypted
from fasas.core.uploads import UploadError, clean_pdf_or_photo

from .models import CredentialType, StaffCredential

STAFF_ROLES = (Role.OPERATOR, Role.COORDINATOR, Role.DOCTOR, Role.ADMINISTRATIVE)


class CredentialError(Exception):
    pass


def add_months(day, months):
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    last = (datetime.date(year + (month == 12), month % 12 + 1, 1) - datetime.timedelta(days=1)).day
    return day.replace(year=year, month=month, day=min(day.day, last))


@dataclass
class Cell:
    type: CredentialType
    credential: StaffCredential | None
    status: str  # valid, expiring, expired, missing, none

    LABELS = {"valid": "in regola", "expiring": "in scadenza", "expired": "scaduto", "missing": "manca", "none": "—"}
    CSS = {"valid": "pill-ok", "expiring": "pill-warn", "expired": "pill-danger", "missing": "pill-danger", "none": ""}

    @property
    def label(self):
        return self.LABELS[self.status]

    @property
    def css(self):
        return self.CSS[self.status]

    @property
    def problem(self):
        return self.status in ("expiring", "expired", "missing")


def status_of(credential_type, credential, user, today=None):
    today = today or timezone.localdate()
    if credential is None:
        return "missing" if credential_type.required_for(user) else "none"
    if credential.expires_on is None:
        return "valid"
    if credential.expires_on < today:
        return "expired"
    if credential.expires_on <= today + datetime.timedelta(days=credential_type.warn_days):
        return "expiring"
    return "valid"


def staff():
    return User.objects.filter(is_active=True, role__in=STAFF_ROLES).order_by("last_name", "first_name")


def latest_by_user(users=None):
    """{(user_id, type_id): registrazione più recente}."""
    latest = {}
    credentials = StaffCredential.objects.select_related("type").order_by("obtained_on", "created_at")
    if users is not None:
        credentials = credentials.filter(user__in=users)
    for credential in credentials:
        latest[(credential.user_id, credential.type_id)] = credential
    return latest


def matrix(users=None, today=None):
    users = list(staff() if users is None else users)
    types = list(CredentialType.objects.filter(active=True))
    latest = latest_by_user(users)
    rows = []
    for user in users:
        cells = [Cell(t, latest.get((user.pk, t.pk)), "") for t in types]
        for cell in cells:
            cell.status = status_of(cell.type, cell.credential, user, today)
        rows.append({"user": user, "cells": cells, "problems": sum(c.problem for c in cells)})
    return {"types": types, "rows": rows,
            "counts": {s: sum(c.status == s for r in rows for c in r["cells"]) for s in ("expired", "expiring", "missing")}}


@transaction.atomic
def add_credential(user, credential_type, obtained_on, by, expires_on=None, provider="", notes="", certificate=None):
    today = timezone.localdate()
    if obtained_on > today:
        raise CredentialError("La data di conseguimento è nel futuro.")
    if expires_on is None and credential_type.validity_months:
        expires_on = add_months(obtained_on, credential_type.validity_months)
    if expires_on is not None and expires_on < obtained_on:
        raise CredentialError("La scadenza precede la data di conseguimento.")
    credential = StaffCredential(user=user, type=credential_type, obtained_on=obtained_on, expires_on=expires_on,
                                 provider=provider.strip(), notes=notes.strip(), created_by=by)
    if certificate is not None:
        try:
            data, content_type = clean_pdf_or_photo(certificate)
        except UploadError as exc:
            raise CredentialError(str(exc)) from None
        credential.certificate_storage = store_encrypted(data, f"personale/{user.pk}")
        credential.certificate_sha256, credential.certificate_type = sha256(data), content_type
    credential.save()
    return credential


def read_certificate(credential, user):
    data = read_encrypted(credential.certificate_storage)
    if sha256(data) != credential.certificate_sha256:
        raise CredentialError("L'attestato non corrisponde all'impronta registrata: possibile alterazione.")
    log_event(AuditLog.Action.DOWNLOAD, credential, user=user)
    return data


def reminders(today=None):
    """Avvisi giornalieri: al coordinatore e all'ufficio amministrativo un riepilogo, a ciascuno le proprie scadenze."""
    from fasas.notifications.models import NotificationKind
    from fasas.notifications.services import notify

    today = today or timezone.localdate()
    data = matrix(today=today)
    problems = []
    for row in data["rows"]:
        for cell in row["cells"]:
            if not cell.problem:
                continue
            problems.append((row["user"], cell))
            expiry = cell.credential.expires_on if cell.credential else None
            when = f" il {expiry:%d/%m/%Y}" if expiry else ""
            text = {"expiring": f"scade{when}", "expired": f"è scaduto{when}", "missing": "non risulta registrato"}
            notify(NotificationKind.MY_DEADLINE, f"{cell.type.name}: {text[cell.status]}",
                   "Porta l'attestato o il giudizio aggiornato al coordinatore o all'ufficio del personale.",
                   link=reverse("staffing:my_credentials"), users=[row["user"]],
                   dedup_key=f"cred-me-{row['user'].pk}-{cell.type.pk}-{cell.status}-{expiry or ''}")
    if problems:
        expired = sum(c.status in ("expired", "missing") for _, c in problems)
        notify(NotificationKind.STAFF_DEADLINES, f"Scadenze del personale: {expired} scadute o mancanti, "
               f"{len(problems) - expired} in scadenza",
               "; ".join(f"{u.get_full_name() or u.username}: {c.type.name} ({c.label})" for u, c in problems[:12]),
               link=reverse("staffing:credentials"), dedup_key=f"cred-{today:%Y-%m-%d}")
    return {"problems": len(problems)}


def export_csv(data):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Dipendente", "Ruolo"] + [f"{t.name} – scadenza" for t in data["types"]] +
                    [f"{t.name} – stato" for t in data["types"]])
    for row in data["rows"]:
        user = row["user"]
        writer.writerow([user.get_full_name() or user.username, user.get_role_display()] +
                        [(c.credential.expires_on.strftime("%d/%m/%Y") if c.credential and c.credential.expires_on
                          else ("senza scadenza" if c.credential else "")) for c in row["cells"]] +
                        [c.label for c in row["cells"]])
    return "﻿" + output.getvalue()
