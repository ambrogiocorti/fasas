import re

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from fasas.core.middleware import client_ip
from fasas.guests.models import Guest

from . import services
from .forms import (
    DistributeForm,
    FieldFormSet,
    SettingsForm,
    SignedForm,
    TemplateForm,
    WithdrawForm,
    answers_from,
    fill_form_class,
)
from .models import FormAssignment, FormSettings, FormSubmission, FormTemplate

MANAGE = "modulistica.manage_forms"
GUEST_VIEW = "modulistica.view_formsubmission"
GUEST_ADD = "modulistica.add_formsubmission"
GUEST_CHANGE = "modulistica.change_formsubmission"


BOLD = re.compile(r"\*\*(.+?)\*\*")


def _bold(value):
    return BOLD.sub(r"<strong>\1</strong>", str(escape(value)))


def form_text(text):
    """Testo del modulo in HTML: paragrafi, elenchi «- », **grassetto** (tutto il resto è testo semplice)."""
    html = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("- ") for line in lines):
            html.append("<ul>" + "".join(f"<li>{_bold(line[2:])}</li>" for line in lines) + "</ul>")
        else:
            html.append(f"<p>{_bold(' '.join(lines))}</p>")
    return mark_safe("".join(html))  # noqa: S308 – testo già passato da escape()


def _pdf(data, name, inline=True):
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{name}.pdf"'
    response["Cache-Control"] = "no-store"
    return response


def _fill_page(request, snap, form, *, action_label, back_url, context=None, preview=False):
    return render(request, "modulistica/fill.html", {
        "snap": snap, "text": form_text(snap["intro"]), "form": form, "back_url": back_url,
        "action_label": action_label, "preview": preview, "settings_obj": FormSettings.get(), **(context or {}),
    })


# --- Amministratore: modelli, intestazione, distribuzione --------------------------------------------------------


@permission_required(MANAGE, raise_exception=True)
def index(request):
    services.ensure_defaults()
    templates = FormTemplate.objects.prefetch_related("fields")
    rows = []
    for t in templates:
        status = services.staff_status(t) if t.for_staff else []
        rows.append({"t": t, "done": sum(1 for a in status if a.submission_id and a.version == t.version),
                     "assigned": len(status), "guest_count": t.submissions.exclude(guest=None).count()})
    return render(request, "modulistica/index.html", {"rows": rows, "settings_obj": FormSettings.get()})


@permission_required(MANAGE, raise_exception=True)
def settings_view(request):
    form = SettingsForm(request.POST or None, instance=FormSettings.get())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Intestazione dei moduli salvata: vale per i moduli compilati da ora in poi.")
        return redirect("modulistica:index")
    return render(request, "generic/form.html", {
        "form": form, "page_title": "Intestazione dei moduli", "cancel_url": reverse("modulistica:index"),
        "intro": "Titolare del trattamento e responsabile della protezione dei dati compaiono in testa ai moduli e "
                 "nelle informative al posto di {titolare}, {sede}, {contatti}, {dpo}, {contatti_dpo}."})


@permission_required(MANAGE, raise_exception=True)
def edit(request, pk=None):
    template = get_object_or_404(FormTemplate, pk=pk) if pk else FormTemplate()
    form = TemplateForm(request.POST or None, instance=template)
    formset = FieldFormSet(request.POST or None, instance=template, prefix="campi")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            if item.pk is None:
                from django.utils.text import slugify

                base, n = slugify(item.title)[:50] or "modulo", 2
                item.code = base
                while FormTemplate.objects.filter(code=item.code).exists():
                    item.code, n = f"{base}-{n}", n + 1
                item.created_by = request.user
            else:
                services.bump_version(item)
            item.updated_by = request.user
            item.save()
            formset.instance = item
            formset.save()
        messages.success(request, f"Modulo salvato (versione {item.version}). "
                                  + ("È visibile a chi lo deve compilare." if item.is_published
                                     else "È una bozza: pubblicarlo quando è pronto."))
        return redirect("modulistica:edit", pk=item.pk)
    return render(request, "modulistica/edit.html", {"form": form, "formset": formset, "template": template,
                                                     "has_default": bool(services.default_for(template.code))})


@require_POST
@permission_required(MANAGE, raise_exception=True)
def set_status(request, pk, status):
    template = get_object_or_404(FormTemplate, pk=pk)
    if status not in FormTemplate.Status.values:
        raise PermissionDenied
    if status == FormTemplate.Status.PUBLISHED and not template.fields.exists():
        messages.error(request, "Aggiungere almeno un campo prima di pubblicare.")
        return redirect("modulistica:edit", pk=pk)
    template.status = status
    if status == FormTemplate.Status.PUBLISHED:
        from django.utils import timezone

        template.published_at = timezone.now()
    template.updated_by = request.user
    template.save()
    messages.success(request, f"Modulo {template.get_status_display().lower()}.")
    return redirect("modulistica:index")


@require_POST
@permission_required(MANAGE, raise_exception=True)
def restore(request, pk):
    template = get_object_or_404(FormTemplate, pk=pk)
    try:
        services.restore_default(template, request.user)
    except services.FormError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Testo e campi predefiniti ripristinati.")
    return redirect("modulistica:edit", pk=pk)


@permission_required(MANAGE, raise_exception=True)
def preview(request, pk):
    template = get_object_or_404(FormTemplate, pk=pk)
    snap = services.snapshot(template)
    form = fill_form_class(snap["fields"], respondent=template.for_guests)()
    return _fill_page(request, snap, form, action_label="Conferma e invia", preview=True,
                      back_url=reverse("modulistica:edit", args=[pk]))


def blank_pdf(request, pk):
    if not (request.user.has_perm(MANAGE) or request.user.has_perm(GUEST_VIEW)):
        raise PermissionDenied
    template = get_object_or_404(FormTemplate, pk=pk)
    return _pdf(services.blank_pdf(template), f"modulo-{template.code}-v{template.version}")


@permission_required(MANAGE, raise_exception=True)
def distribute(request, pk):
    template = get_object_or_404(FormTemplate, pk=pk, for_staff=True)
    form = DistributeForm(request.POST or None, initial={"roles": template.staff_roles})
    if request.method == "POST" and form.is_valid():
        try:
            count = services.distribute(template, form.cleaned_data["roles"], request.user,
                                        form.cleaned_data["due_date"])
        except services.FormError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Modulo inviato a {count} person{'a' if count == 1 else 'e'}: chi non "
                                      "l'aveva lo riceve, chi deve ancora compilarlo riceve un promemoria, "
                                      "chi l'ha già compilato non riceve nulla.")
            return redirect("modulistica:distribute", pk=pk)
    return render(request, "modulistica/distribute.html", {
        "template": template, "form": form, "status": services.staff_status(template)})


# --- Ogni utente del personale: i miei moduli -------------------------------------------------------------------


def mine(request):
    return render(request, "modulistica/mine.html", {
        "pending": services.pending_for(request.user),
        "done": FormSubmission.objects.filter(subject_user=request.user).select_related("template"),
    })


def fill_assignment(request, pk):
    assignment = get_object_or_404(FormAssignment.objects.select_related("template"), pk=pk, user=request.user,
                                   submission__isnull=True, cancelled=False)
    template = assignment.template
    snap = services.snapshot(template, user=request.user)
    form = fill_form_class(snap["fields"])(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit(template, answers_from(form, snap["fields"]), request.user, subject_user=request.user,
                            respondent=request.user.get_full_name() or request.user.username,
                            ip=client_ip(request), assignment=assignment)
        except services.FormError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Modulo inviato. Ne trovi la copia in PDF qui sotto.")
            return redirect("modulistica:mine")
    return _fill_page(request, snap, form, action_label="Conferma e invia", back_url=reverse("modulistica:mine"))


# --- Ospiti (coordinatore, ufficio amministrativo) -----------------------------------------------------------------


@permission_required(GUEST_VIEW, raise_exception=True)
def overview(request):
    pending = (FormSubmission.objects.exclude(guest=None).filter(signed_at__isnull=True, withdrawn_at__isnull=True)
               .select_related("guest", "template"))
    pending = [s for s in pending if s.needs_signature]
    return render(request, "modulistica/overview.html", {
        "pending": pending, "templates": FormTemplate.objects.filter(status="published", for_guests=True)})


@permission_required(GUEST_VIEW, raise_exception=True)
def guest_view(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    return render(request, "modulistica/guest.html", {
        "guest": guest, "active_tab": "forms",
        "submissions": guest.form_submissions.select_related("template", "created_by", "family_link__user"),
        "templates": FormTemplate.objects.filter(status=FormTemplate.Status.PUBLISHED, for_guests=True),
    })


@permission_required(GUEST_ADD, raise_exception=True)
def guest_fill(request, guest_pk, template_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    template = get_object_or_404(FormTemplate, pk=template_pk, for_guests=True, status=FormTemplate.Status.PUBLISHED)
    snap = services.snapshot(template, guest=guest)
    # chi risponde: dai campi «nome» e «qualita» del modulo, se ci sono; altrimenti due domande in più
    own = {f["key"] for f in snap["fields"]} >= {"nome", "qualita"}
    form = fill_form_class(snap["fields"], respondent=not own)(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            submission = services.submit(
                template, answers_from(form, snap["fields"]), request.user, guest=guest,
                respondent=data["nome"] if own else data["respondent"],
                respondent_role=data["qualita"] if own else data["respondent_role"], ip=client_ip(request))
        except services.FormError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Modulo registrato e salvato nei documenti dell'ospite."
                                      + (" Stampare il PDF, farlo firmare e caricare la scansione."
                                         if submission.needs_signature else ""))
            return redirect("modulistica:guest", guest_pk=guest.pk)
    return _fill_page(request, snap, form, action_label="Registra", context={"guest": guest},
                      back_url=reverse("modulistica:guest", args=[guest.pk]))


def _can_see(user, submission):
    if submission.guest_id:
        return user.has_perm(GUEST_VIEW)
    if submission.subject_user_id == user.pk:
        return True
    return user.has_perm(MANAGE)


def submission_pdf(request, pk, signed=False):
    submission = get_object_or_404(FormSubmission.objects.select_related("template", "guest"), pk=pk)
    if not _can_see(request.user, submission):
        raise PermissionDenied
    if signed and not submission.signed_storage:
        raise PermissionDenied
    try:
        data = services.read_pdf(submission, request.user, signed=signed)
    except services.FormError as exc:
        messages.error(request, str(exc))
        return redirect("core:dashboard")
    if signed and submission.signed_type != "application/pdf":
        response = HttpResponse(data, content_type=submission.signed_type)
        response["Cache-Control"] = "no-store"
        return response
    return _pdf(data, f"{submission.template.code}-{submission.pk}{'-firmato' if signed else ''}")


def signed_upload(request, pk):
    submission = get_object_or_404(FormSubmission.objects.select_related("template", "guest"), pk=pk)
    allowed = request.user.has_perm(GUEST_CHANGE) if submission.guest_id else request.user.has_perm(MANAGE)
    if not allowed:
        raise PermissionDenied
    form = SignedForm(request.POST or None, request.FILES or None)
    back = (reverse("modulistica:guest", args=[submission.guest_id]) if submission.guest_id
            else reverse("modulistica:distribute", args=[submission.template_id]))
    if request.method == "POST" and form.is_valid():
        try:
            services.attach_signed(submission, form.cleaned_data["file"], request.user)
        except services.FormError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Scansione del modulo firmato salvata.")
            return redirect(back)
    return render(request, "generic/form.html", {
        "form": form, "page_title": f"Modulo firmato: {submission.snapshot.get('title')}", "multipart": True,
        "guest": submission.guest, "cancel_url": back, "submit_label": "Carica",
        "intro": "Caricare la scansione o la foto del modulo stampato e firmato. Resta l'originale cartaceo da "
                 "conservare secondo le regole della struttura."})


def withdraw_view(request, pk):
    submission = get_object_or_404(FormSubmission.objects.select_related("template", "guest"), pk=pk)
    allowed = request.user.has_perm(GUEST_CHANGE) if submission.guest_id else request.user.has_perm(MANAGE)
    if not allowed:
        raise PermissionDenied
    form = WithdrawForm(request.POST or None)
    back = reverse("modulistica:guest", args=[submission.guest_id]) if submission.guest_id else reverse("modulistica:index")
    if request.method == "POST" and form.is_valid():
        try:
            services.withdraw(submission, request.user, form.cleaned_data["reason"])
        except services.FormError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Revoca registrata.")
            return redirect(back)
    return render(request, "generic/form.html", {
        "form": form, "page_title": f"Revoca: {submission.snapshot.get('title')}", "guest": submission.guest,
        "cancel_url": back, "submit_label": "Registra la revoca", "danger": True})


# --- Familiari (area familiari) ----------------------------------------------------------------------------------


@permission_required("families.use_family_area", raise_exception=True)
def family_fill(request, link_pk, template_pk):
    from fasas.families.services import link_for

    link = link_for(request.user, link_pk)
    template = get_object_or_404(FormTemplate, pk=template_pk, for_family=True, status=FormTemplate.Status.PUBLISHED)
    snap = services.snapshot(template, guest=link.guest)
    form = fill_form_class(snap["fields"])(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit(template, answers_from(form, snap["fields"]), request.user, guest=link.guest,
                            family_link=link, respondent=request.user.get_full_name() or request.user.username,
                            respondent_role=link.get_relation_display(), ip=client_ip(request))
        except services.FormError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Modulo inviato alla struttura.")
            return redirect("families:guest", pk=link.pk)
    return _fill_page(request, snap, form, action_label="Conferma e invia",
                      back_url=reverse("families:guest", args=[link.pk]))


@permission_required("families.use_family_area", raise_exception=True)
def family_pdf(request, link_pk, pk):
    from fasas.families.services import link_for

    link = link_for(request.user, link_pk)
    submission = get_object_or_404(FormSubmission, pk=pk, family_link=link)
    return _pdf(services.read_pdf(submission, request.user), f"{submission.template.code}-{submission.pk}")


