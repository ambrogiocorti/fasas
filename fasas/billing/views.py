from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST

from fasas.guests.models import Guest

from . import exports, services
from .forms import CloseMonthForm, CorrectionForm, FeeLineForm, PaymentForm, ReasonForm, SettingsForm
from .models import AttendanceMonth, AttendanceStatus, BillingSettings, FeeStatement, GuestFeeLine

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _month(request):
    return services.parse_month(request.GET.get("mese") or request.POST.get("mese"))


def _month_url(name, first):
    return f"{reverse(name)}?mese={first:%Y-%m}"


@permission_required("billing.view_attendancemonth", raise_exception=True)
def attendance_view(request):
    first = _month(request)
    month, rows = services.attendance(first)
    days = services.month_days(first)
    today = timezone.localdate()
    totals = {k: sum(r[2][k] for r in rows) for k in ("present", "hospital", "family", "absent")}
    return render(request, "billing/attendance.html", {
        "first": first, "month": month, "rows": rows, "days": days, "totals": totals,
        "label": exports.month_label(first), "prev": services.shift_month(first, -1),
        "next": services.shift_month(first, 1), "today": today, "statuses": AttendanceStatus.choices,
        "can_close": services.month_end(first) < today and not (month and month.is_closed),
        "close_form": CloseMonthForm(), "reopen_form": ReasonForm(),
        "weekend": {d.day for d in days if d.weekday() >= 5},
    })


@permission_required("billing.add_attendancecorrection", raise_exception=True)
def correction(request, guest_pk):
    guest = get_object_or_404(Guest, pk=guest_pk)
    initial = {"date": request.GET.get("giorno") or timezone.localdate(), "status": request.GET.get("stato")}
    form = CorrectionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.save_correction(guest, data["date"], data["status"], data["reason"], request.user)
        except services.BillingError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Presenza di {guest} del {data['date']:%d/%m/%Y} corretta.")
            return redirect(_month_url("billing:attendance", services.month_start(data["date"])))
    return render(request, "generic/form.html", {
        "form": form, "page_title": f"Correzione presenze – {guest}",
        "intro": "La correzione prevale su quanto risulta dai movimenti (ingresso, ricovero, rientro, dimissione) "
                 "ed è registrata nell'audit log. Quando possibile, registrare invece il movimento nella cartella.",
        "cancel_url": reverse("billing:attendance"),
    })


@require_POST
@permission_required("billing.close_attendance", raise_exception=True)
def close_month_view(request):
    first = _month(request)
    form = CloseMonthForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Confermare di aver controllato le presenze.")
    else:
        try:
            services.close_month(first, request.user, form.cleaned_data["notes"])
        except services.BillingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Presenze di {exports.month_label(first)} chiuse.")
    return redirect(_month_url("billing:attendance", first))


@require_POST
@permission_required("billing.close_attendance", raise_exception=True)
def reopen_month_view(request):
    first = _month(request)
    month = get_object_or_404(AttendanceMonth, month=first)
    form = ReasonForm(request.POST)
    try:
        if not form.is_valid():
            raise services.BillingError("Indicare il motivo della riapertura.")
        services.reopen_month(month, request.user, form.cleaned_data["reason"])
    except services.BillingError as exc:
        messages.error(request, str(exc))
    else:
        messages.warning(request, f"Presenze di {exports.month_label(first)} riaperte.")
    return redirect(_month_url("billing:attendance", first))


@permission_required("billing.view_attendancemonth", raise_exception=True)
def attendance_excel(request):
    first = _month(request)
    response = HttpResponse(exports.attendance_workbook(first), content_type=XLSX)
    response["Content-Disposition"] = content_disposition_header(True, f"presenze-{first:%Y-%m}.xlsx")
    return response


@permission_required("billing.view_guestfeeline", raise_exception=True)
def fees(request):
    today = timezone.localdate()
    guests = Guest.objects.exclude(status=Guest.Status.ARCHIVED).prefetch_related("fee_lines")
    rows = []
    for guest in guests:
        lines = sorted(guest.fee_lines.all(), key=lambda f: (f.valid_to is not None and f.valid_to < today, f.payer))
        current = [f for f in lines if f.valid_on(today)]
        rows.append({"guest": guest, "lines": lines, "daily": sum(f.daily_rate for f in current)})
    return render(request, "billing/fees.html", {"rows": rows, "today": today})


@permission_required("billing.view_guestfeeline", raise_exception=True)
def fee_edit(request, guest_pk=None, pk=None):
    line = get_object_or_404(GuestFeeLine, pk=pk) if pk else None
    guest = line.guest if line else get_object_or_404(Guest, pk=guest_pk)
    perm = "billing.change_guestfeeline" if line else "billing.add_guestfeeline"
    if not request.user.has_perm(perm):
        messages.error(request, "Non hai il permesso di modificare le rette.")
        return redirect("billing:fees")
    initial = {"valid_from": services.month_start()} if not line else None
    form = FeeLineForm(request.POST or None, instance=line, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.instance.guest = guest
        form.save()
        messages.success(request, f"Voce di retta di {guest} salvata.")
        return redirect("billing:fees")
    return render(request, "generic/form.html", {
        "form": form, "page_title": f"{'Modifica voce' if line else 'Nuova voce'} di retta – {guest}",
        "intro": "Una voce per ogni pagante (es. quota sanitaria ATS, quota sociale del Comune, quota a carico della "
                 "famiglia). Per un cambio di tariffa chiudere la voce attuale con la data di fine e crearne una nuova.",
        "cancel_url": reverse("billing:fees"),
    })


@permission_required("billing.view_feestatement", raise_exception=True)
def statements(request):
    first = _month(request)
    month = AttendanceMonth.objects.filter(month=first).first()
    qs = FeeStatement.objects.filter(month=month).select_related("guest").prefetch_related("payments") \
        if month else FeeStatement.objects.none()
    status = request.GET.get("stato")
    if status in FeeStatement.Status.values:
        qs = qs.filter(status=status)
    overdue = FeeStatement.objects.filter(status=FeeStatement.Status.ISSUED, due_date__lt=timezone.localdate()) \
        .select_related("guest", "month").order_by("due_date")[:20]
    summary = qs.exclude(status=FeeStatement.Status.CANCELLED).aggregate(total=Sum("total"), n=Count("pk"))
    return render(request, "billing/statements.html", {
        "first": first, "month": month, "statements": qs, "label": exports.month_label(first), "overdue": overdue,
        "prev": services.shift_month(first, -1), "next": services.shift_month(first, 1), "summary": summary,
        "drafts": qs.filter(status=FeeStatement.Status.DRAFT).count(), "statuses": FeeStatement.Status.choices,
        "status": status,
    })


@require_POST
@permission_required("billing.add_feestatement", raise_exception=True)
def generate(request):
    first = _month(request)
    month = AttendanceMonth.objects.filter(month=first).first()
    try:
        if month is None:
            raise services.BillingError("Chiudere prima le presenze del mese.")
        created, skipped, missing = services.generate_statements(month, request.user)
    except services.BillingError as exc:
        messages.error(request, str(exc))
    else:
        text = f"{len(created)} prospetti in bozza generati"
        if skipped:
            text += f", {skipped} già emessi lasciati invariati"
        messages.success(request, text + ".")
        if missing:
            messages.warning(request, "Ospiti senza voci di retta: " + ", ".join(str(g) for g in missing) + ".")
    return redirect(_month_url("billing:statements", first))


@require_POST
@permission_required("billing.issue_statement", raise_exception=True)
def issue_all(request):
    first = _month(request)
    count = 0
    for statement in FeeStatement.objects.filter(month__month=first, status=FeeStatement.Status.DRAFT) \
            .order_by("guest__last_name", "guest__first_name", "payer_name"):
        services.issue_statement(statement, request.user)
        count += 1
    messages.success(request, f"{count} prospetti emessi.")
    return redirect(_month_url("billing:statements", first))


@permission_required("billing.view_feestatement", raise_exception=True)
def statement_detail(request, pk):
    statement = get_object_or_404(FeeStatement.objects.select_related("guest", "month"), pk=pk)
    form = PaymentForm(request.POST or None, statement=statement)
    if request.method == "POST":
        if not request.user.has_perm("billing.add_feepayment"):
            messages.error(request, "Non hai il permesso di registrare incassi.")
        elif form.is_valid():
            data = form.cleaned_data
            try:
                services.register_payment(statement, data["amount"], data["date"], data["method"], data["reference"],
                                          request.user)
            except services.BillingError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "Incasso registrato.")
                return redirect(statement.get_absolute_url())
    return render(request, "billing/statement.html", {
        "statement": statement, "payment_form": form, "cancel_form": ReasonForm(),
        "payments": statement.payments.select_related("created_by"),
    })


@require_POST
@permission_required("billing.issue_statement", raise_exception=True)
def statement_issue(request, pk):
    statement = get_object_or_404(FeeStatement, pk=pk)
    try:
        statement = services.issue_statement(statement, request.user)
    except services.BillingError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Prospetto {statement.number} emesso.")
    return redirect(statement.get_absolute_url())


@require_POST
@permission_required("billing.issue_statement", raise_exception=True)
def statement_cancel(request, pk):
    statement = get_object_or_404(FeeStatement, pk=pk)
    first = statement.month.month
    form = ReasonForm(request.POST)
    try:
        if not form.is_valid():
            raise services.BillingError("Indicare il motivo dell'annullamento.")
        result = services.cancel_statement(statement, request.user, form.cleaned_data["reason"])
    except services.BillingError as exc:
        messages.error(request, str(exc))
        return redirect(statement.get_absolute_url())
    messages.warning(request, "Bozza eliminata." if result is None else f"Prospetto {statement.number} annullato.")
    return redirect(_month_url("billing:statements", first))


@permission_required("billing.view_feestatement", raise_exception=True)
def statement_pdf_view(request, pk):
    statement = get_object_or_404(FeeStatement.objects.select_related("guest", "month"), pk=pk)
    response = HttpResponse(exports.statement_pdf(statement, request.user), content_type="application/pdf")
    name = (statement.number or f"bozza-{statement.pk}").replace("/", "-")
    response["Content-Disposition"] = content_disposition_header(False, f"prospetto-{name}.pdf")
    return response


@permission_required("billing.view_feestatement", raise_exception=True)
def statements_excel(request):
    first = _month(request)
    month = get_object_or_404(AttendanceMonth, month=first)
    response = HttpResponse(exports.statements_workbook(month), content_type=XLSX)
    response["Content-Disposition"] = content_disposition_header(True, f"prospetti-{first:%Y-%m}.xlsx")
    return response


@permission_required("billing.change_billingsettings", raise_exception=True)
def settings_view(request):
    form = SettingsForm(request.POST or None, instance=BillingSettings.get())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Impostazioni salvate.")
        return redirect("billing:settings")
    return render(request, "generic/form.html", {
        "form": form, "page_title": "Impostazioni presenze e rette", "cancel_url": reverse("billing:attendance"),
        "intro": "Regole di conteggio dei giorni e dati dell'ente gestore stampati sui prospetti. Le regole vanno "
                 "verificate con l'ATS e con il contratto/convenzione della struttura.",
    })


def billing_overview():
    """Numeri per il cruscotto dell'ufficio amministrativo."""
    today = timezone.localdate()
    current = services.month_start(today)
    previous = services.shift_month(current, -1)
    prev_month = AttendanceMonth.objects.filter(month=previous).first()
    issued = FeeStatement.objects.filter(status__in=[FeeStatement.Status.ISSUED, FeeStatement.Status.PAID])
    open_statements = FeeStatement.objects.filter(status=FeeStatement.Status.ISSUED).prefetch_related("payments")
    guests = Guest.objects.exclude(status=Guest.Status.ARCHIVED)
    without_fees = [g for g in guests.annotate(n=Count("fee_lines", filter=Q(fee_lines__valid_to__isnull=True)
                                                        | Q(fee_lines__valid_to__gte=today))) if not g.n]
    return {
        "current": current, "previous": previous, "prev_month": prev_month,
        "current_rows": services.attendance(current)[1],
        "drafts": FeeStatement.objects.filter(status=FeeStatement.Status.DRAFT).count(),
        "issued_month": issued.filter(issue_date__gte=current).aggregate(total=Sum("total"))["total"] or 0,
        "receivable": sum((s.balance for s in open_statements), 0),
        "overdue": [s for s in open_statements.select_related("guest") if s.is_overdue][:10],
        "without_fees": without_fees,
    }
