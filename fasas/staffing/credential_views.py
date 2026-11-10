"""Pagine delle scadenze del personale: quadro per coordinatore e ufficio, storico per dipendente, le mie scadenze."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from fasas.accounts.models import User

from . import credentials as services
from .forms import CredentialForm, CredentialTypeForm
from .models import CredentialType, StaffCredential


@permission_required("staffing.view_staffcredential", raise_exception=True)
def overview(request):
    data = services.matrix()
    if request.GET.get("formato") == "csv":
        response = HttpResponse(services.export_csv(data), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="scadenze-personale-{timezone.localdate():%Y%m%d}.csv"'
        return response
    only_problems = request.GET.get("problemi") == "1"
    rows = [r for r in data["rows"] if r["problems"]] if only_problems else data["rows"]
    return render(request, "staffing/credentials.html", {**data, "rows": rows, "only_problems": only_problems})


@permission_required("staffing.add_staffcredential", raise_exception=True)
def create(request):
    users = list(services.staff())
    initial = {"obtained_on": timezone.localdate(), "user": request.GET.get("utente"), "type": request.GET.get("tipo")}
    form = CredentialForm(request.POST or None, request.FILES or None, users=users, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            credential = services.add_credential(data["user"], data["type"], data["obtained_on"], request.user,
                                                 data["expires_on"], data["provider"], data["notes"],
                                                 data.get("certificate"))
        except services.CredentialError as exc:
            form.add_error(None, str(exc))
        else:
            expiry = f"scade il {credential.expires_on:%d/%m/%Y}" if credential.expires_on else "senza scadenza"
            messages.success(request, f"{credential.type} registrato per {credential.user}: {expiry}.")
            return redirect("staffing:credential_user", user_pk=credential.user_id)
    return render(request, "generic/form.html", {
        "form": form, "page_title": "Registra un corso, un'idoneità o una visita", "submit_label": "Registra",
        "multipart": True, "cancel_url": reverse("staffing:credentials"),
        "intro": "L'attestato si conserva cifrato. Per l'idoneità alla mansione basta il giudizio consegnato al "
                 "datore di lavoro: non caricare la cartella sanitaria e di rischio."})


def _history(person):
    data = services.matrix([person])
    return {"person": person, "cells": data["rows"][0]["cells"],
            "history": StaffCredential.objects.filter(user=person).select_related("type", "created_by")}


@permission_required("staffing.view_staffcredential", raise_exception=True)
def user_view(request, user_pk):
    person = get_object_or_404(User, pk=user_pk)
    return render(request, "staffing/credential_user.html", _history(person))


@login_required
def mine(request):
    return render(request, "staffing/credential_user.html", {**_history(request.user), "mine": True})


@login_required
def certificate(request, pk):
    credential = get_object_or_404(StaffCredential.objects.select_related("user"), pk=pk, certificate_storage__gt="")
    if credential.user_id != request.user.pk and not request.user.has_perm("staffing.view_staffcredential"):
        raise PermissionDenied
    try:
        data = services.read_certificate(credential, request.user)
    except services.CredentialError as exc:
        messages.error(request, str(exc))
        return redirect("staffing:credentials")
    extension = "pdf" if credential.certificate_type == "application/pdf" else "jpg"
    response = HttpResponse(data, content_type=credential.certificate_type)
    response["Content-Disposition"] = f'inline; filename="attestato-{credential.pk}.{extension}"'
    response["Cache-Control"] = "no-store"
    return response


@require_POST
@permission_required("staffing.delete_staffcredential", raise_exception=True)
def delete(request, pk):
    credential = get_object_or_404(StaffCredential, pk=pk)
    user_pk = credential.user_id
    credential.delete()  # resta traccia nell'audit (chi, quando, valori precedenti)
    messages.success(request, "Registrazione eliminata.")
    return redirect("staffing:credential_user", user_pk=user_pk)


@permission_required("staffing.view_credentialtype", raise_exception=True)
def types(request):
    return render(request, "staffing/credential_types.html", {"types": CredentialType.objects.all()})


@permission_required("staffing.change_credentialtype", raise_exception=True)
def type_edit(request, pk=None):
    instance = get_object_or_404(CredentialType, pk=pk) if pk else None
    if instance is None and not request.user.has_perm("staffing.add_credentialtype"):
        raise PermissionDenied
    form = CredentialTypeForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tipo di scadenza salvato.")
        return redirect("staffing:credential_types")
    return render(request, "generic/form.html", {
        "form": form, "page_title": f"Modifica: {instance}" if instance else "Nuovo tipo di scadenza",
        "cancel_url": reverse("staffing:credential_types"),
        "intro": "Le periodicità proposte sono indicative: confermarle con l'RSPP e il medico competente."})
