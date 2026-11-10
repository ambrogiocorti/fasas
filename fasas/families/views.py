import datetime

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from fasas.core.modules import is_on
from fasas.guests.models import Guest

from . import services
from .forms import DecisionForm, LinkForm, MessageForm, RevokeForm, ShareForm, VisitForm
from .models import FamilyLink, SharedDocument, VisitRequest

# --- Familiare o tutore ---------------------------------------------------------------------------------------


@permission_required("families.use_family_area", raise_exception=True)
def home(request):
    links = list(services.links_for(request.user))
    if len(links) == 1:
        return redirect("families:guest", pk=links[0].pk)
    for link in links:
        link.unread = link.messages.filter(from_family=False, read_at__isnull=True).count()
        link.next_visit = link.visits.filter(status=VisitRequest.Status.CONFIRMED,
                                             day__gte=timezone.localdate()).first()
    return render(request, "families/home.html", {"links": links})


@permission_required("families.use_family_area", raise_exception=True)
def guest_view(request, pk):
    link = services.link_for(request.user, pk)
    message_form = MessageForm(request.POST if "body" in request.POST else None)
    visit_form = VisitForm(request.POST if "day" in request.POST else None)
    if request.method == "POST":
        try:
            if "body" in request.POST and message_form.is_valid():
                services.send_message(link, request.user, message_form.cleaned_data["body"], from_family=True)
                messages.success(request, "Messaggio inviato alla struttura.")
                return redirect("families:guest", pk=link.pk)
            if "day" in request.POST and visit_form.is_valid():
                d = visit_form.cleaned_data
                services.request_visit(link, request.user, d["day"], d["time"], d["people"], d["notes"])
                messages.success(request, "Richiesta di visita inviata: riceverai la conferma qui e tra le notifiche.")
                return redirect("families:guest", pk=link.pk)
        except services.FamilyError as exc:
            messages.error(request, str(exc))
    services.mark_read(link, request.user, from_family=False)
    cash = None
    if link.can_see_cash and is_on("personal"):
        from fasas.personal.services import balance

        cash = balance(link.guest)
    return render(request, "families/guest.html", {
        "link": link, "guest": link.guest, "thread": link.messages.select_related("author"),
        "visits": link.visits.filter(day__gte=timezone.localdate() - datetime.timedelta(days=30)).order_by("-day"),
        "documents": services.shared_documents(link), "cash": cash, "today": timezone.localdate(),
        "message_form": message_form, "visit_form": visit_form,
    })


@permission_required("families.use_family_area", raise_exception=True)
def document_view(request, pk, share_pk):
    from fasas.documents.services import read_version

    link = services.link_for(request.user, pk)
    share = next((s for s in services.shared_documents(link) if s.pk == share_pk), None)
    if share is None:
        messages.error(request, "Documento non disponibile.")
        return redirect("families:guest", pk=link.pk)
    version = share.document.current_version
    data = read_version(version, user=request.user)  # resta nell'audit: chi ha aperto cosa e quando
    response = HttpResponse(data, content_type=version.content_type or "application/octet-stream")
    extension = version.original_name.rsplit(".", 1)[-1].lower() if "." in version.original_name else "bin"
    response["Content-Disposition"] = f'inline; filename="documento-{share.document.pk}.{extension}"'
    response["Cache-Control"] = "no-store"
    return response


@permission_required("families.use_family_area", raise_exception=True)
def cash_statement(request, pk):
    link = services.link_for(request.user, pk)
    if not (link.can_see_cash and is_on("personal")):
        messages.error(request, "Il rendiconto della cassa non è disponibile per il tuo collegamento.")
        return redirect("families:guest", pk=link.pk)
    from fasas.personal.services import statement_pdf

    today = timezone.localdate()
    try:
        month = datetime.date.fromisoformat(request.GET.get("mese", "") + "-01")
    except ValueError:
        month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    end = min((month + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1), today)
    if month > today:
        month = today.replace(day=1)
    pdf = statement_pdf(link.guest, month, end, request.user)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="rendiconto-{month:%Y-%m}.pdf"'
    return response


@require_POST
@permission_required("families.use_family_area", raise_exception=True)
def visit_cancel(request, pk, visit_pk):
    link = services.link_for(request.user, pk)
    visit = get_object_or_404(VisitRequest, pk=visit_pk, link=link)
    try:
        services.cancel_visit(visit, request.user)
    except services.FamilyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Visita annullata.")
    return redirect("families:guest", pk=link.pk)


# --- Struttura (coordinatore) -------------------------------------------------------------------------------


@permission_required("families.manage_family_area", raise_exception=True)
def staff_home(request):
    links = (FamilyLink.objects.select_related("user", "guest").exclude(guest__status="archived")
             .order_by("guest__last_name", "user__last_name"))
    for link in links:
        link.unread = link.messages.filter(from_family=True, read_at__isnull=True).count()
    return render(request, "families/staff_home.html", {
        "links": links, "unread_links": [link for link in links if link.unread],
        "pending": VisitRequest.objects.filter(status=VisitRequest.Status.PENDING, day__gte=timezone.localdate())
        .select_related("link__guest", "link__user"),
        "upcoming": VisitRequest.objects.filter(status=VisitRequest.Status.CONFIRMED, day__gte=timezone.localdate())
        .select_related("link__guest", "link__user")[:30],
        "decision_form": DecisionForm(),
    })


@permission_required("families.manage_family_area", raise_exception=True)
def staff_guest(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    form = ShareForm(request.POST or None, guest=guest)
    if request.method == "POST" and form.is_valid():
        try:
            services.share_document(form.cleaned_data["document"], request.user, form.cleaned_data["note"])
        except services.FamilyError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Documento condiviso con i familiari autorizzati a vedere i documenti.")
        return redirect("families:staff_guest", guest_pk=guest.pk)
    return render(request, "families/staff_guest.html", {
        "guest": guest, "active_tab": "families", "links": guest.family_links.select_related("user"),
        "shares": SharedDocument.objects.filter(document__guest=guest, revoked_at__isnull=True)
        .select_related("document", "shared_by"),
        "share_form": form,
    })


@permission_required("families.manage_family_area", raise_exception=True)
def staff_link(request, pk):
    link = get_object_or_404(FamilyLink.objects.select_related("user", "guest"), pk=pk)
    services.mark_read(link, request.user, from_family=True)  # chi apre la conversazione la legge
    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.send_message(link, request.user, form.cleaned_data["body"], from_family=False)
        except services.FamilyError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Risposta inviata.")
        return redirect("families:staff_link", pk=link.pk)
    return render(request, "families/staff_link.html", {
        "link": link, "guest": link.guest, "thread": link.messages.select_related("author", "read_by"),
        "visits": link.visits.order_by("-day")[:20], "form": form, "decision_form": DecisionForm(),
    })


@permission_required("families.manage_family_area", raise_exception=True)
def link_edit(request, pk=None):
    link = get_object_or_404(FamilyLink, pk=pk) if pk else None
    initial = {"guest": request.GET.get("ospite")} if link is None else None
    form = LinkForm(request.POST or None, instance=link, initial=initial)
    if request.method == "POST" and form.is_valid():
        link = form.save(commit=False)
        if link.pk is None:
            link.created_by = request.user
        link.updated_by = request.user
        link.save()
        messages.success(request, "Collegamento salvato: il familiare vede l'ospite alla prossima apertura.")
        return redirect("families:staff_guest", guest_pk=link.guest_id)
    return render(request, "generic/form.html", {
        "form": form, "page_title": "Modifica collegamento" if link else "Collega un familiare o un tutore",
        "cancel_url": reverse("families:staff_home"),
        "intro": "Collegare solo con il consenso dell'ospite o con il decreto di nomina del tutore o "
                 "dell'amministratore di sostegno, e secondo le indicazioni del DPO. Il familiare non vede mai la "
                 "cartella clinica: solo messaggi, visite e i documenti condivisi uno per uno."})


@permission_required("families.manage_family_area", raise_exception=True)
def link_revoke(request, pk):
    link = get_object_or_404(FamilyLink.objects.select_related("guest"), pk=pk)
    form = RevokeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.revoke_link(link, request.user, form.cleaned_data["reason"])
        messages.success(request, "Collegamento revocato: il familiare non vede più l'ospite.")
        return redirect("families:staff_guest", guest_pk=link.guest_id)
    return render(request, "generic/form.html", {
        "form": form, "page_title": f"Revoca: {link}", "submit_label": "Revoca", "danger": True,
        "guest": link.guest, "cancel_url": reverse("families:staff_guest", args=[link.guest_id])})


@require_POST
@permission_required("families.manage_family_area", raise_exception=True)
def visit_decide(request, pk):
    visit = get_object_or_404(VisitRequest.objects.select_related("link"), pk=pk)
    form = DecisionForm(request.POST)
    form.is_valid()
    try:
        services.decide_visit(visit, request.user, request.POST.get("confirm") == "1", form.cleaned_data.get("note", ""))
    except services.FamilyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Risposta inviata al familiare.")
    target = request.POST.get("next", "")
    return redirect(target if target.startswith("/famiglie/gestione/") else "families:staff_home")


@require_POST
@permission_required("families.manage_family_area", raise_exception=True)
def unshare(request, pk):
    share = get_object_or_404(SharedDocument, pk=pk, revoked_at__isnull=True)
    services.unshare_document(share, request.user)
    messages.success(request, "Il documento non è più visibile ai familiari.")
    return redirect("families:staff_guest", guest_pk=share.document.guest_id)
