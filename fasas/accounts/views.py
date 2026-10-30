from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.middleware import client_ip
from fasas.core.views_mixins import FormPageMixin, PermRequiredMixin

from . import twofactor
from .forms import AdminSetPasswordForm, LoginForm, OTPForm, ProfileForm, UserCreateForm, UserForm
from .models import AccessLog, User, UserPermissionOverride
from .roles import MANAGED_APPS
from .services import is_locked_out, record_access


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        """Dopo la password, se serve, il secondo passaggio: l'accesso si completa solo con il codice dell'app."""
        user = form.get_user()
        need = twofactor.requirement(user, self.request)
        if need == "none":
            return super().form_valid(form)
        if need == "refused":
            record_access(self.request, AccessLog.Event.FAILED, user.get_username(), user)
            form.add_error(None, "Da fuori dalla rete della struttura serve la verifica in due passaggi: "
                                 "attivala la prima volta da un computer della struttura.")
            return self.form_invalid(form)
        twofactor.start_pending(self.request, user, self.get_success_url())
        return redirect("accounts:otp_verify" if need == "verify" else "accounts:otp_setup")


def _finish_login(request, user, next_url):
    twofactor.clear_pending(request)
    auth_login(request, user, backend=user.backend)
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("core:dashboard")
    return next_url


def otp_verify(request):
    """Secondo passaggio dell'accesso: codice dell'app o codice di recupero."""
    user, next_url = twofactor.pending_user(request)
    if user is None:
        messages.warning(request, "Tempo scaduto: inserisci di nuovo nome utente e password.")
        return redirect("accounts:login")
    form = OTPForm(request.POST or None)
    if request.method == "POST":
        if is_locked_out(user.get_username(), client_ip(request)):
            record_access(request, AccessLog.Event.LOCKED, user.get_username(), user)
            twofactor.clear_pending(request)
            messages.error(request, "Troppi tentativi falliti. Riprova tra qualche minuto o contatta l'amministratore.")
            return redirect("accounts:login")
        if form.is_valid():
            method = twofactor.verify(user, form.cleaned_data["code"])
            if method:
                target = _finish_login(request, user, next_url)
                if method == "recovery":
                    left = twofactor.recovery_codes_left(user)
                    messages.warning(request, f"Hai usato un codice di recupero: ne restano {left}. "
                                              "Se hai perso il telefono chiedi all'amministratore di reimpostare la verifica.")
                return redirect(target)
            record_access(request, AccessLog.Event.OTP_FAILED, user.get_username(), user)
            form.add_error("code", "Codice non valido o già usato. Controlla che l'ora del telefono sia corretta.")
    return render(request, "accounts/otp_verify.html", {"form": form, "pending": user})


def otp_setup(request):
    """Attivazione: QR code da inquadrare con l'app, poi conferma con il primo codice."""
    pending, next_url = twofactor.pending_user(request)
    user = pending or (request.user if request.user.is_authenticated else None)
    if user is None:
        return redirect("accounts:login")
    if pending is None and twofactor.is_enrolled(user):
        return redirect("accounts:security")
    if not twofactor.from_trusted_network(request):
        messages.error(request, "La verifica in due passaggi si attiva solo dalla rete della struttura.")
        return redirect("accounts:login" if pending else "accounts:security")
    secret = request.session.get(twofactor.SESSION_SETUP) or twofactor.new_secret()
    request.session[twofactor.SESSION_SETUP] = secret
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        codes = twofactor.enroll(user, secret, form.cleaned_data["code"])
        if codes:
            request.session.pop(twofactor.SESSION_SETUP, None)
            target = _finish_login(request, user, next_url) if pending else reverse("accounts:security")
            return render(request, "accounts/otp_codes.html", {"codes": codes, "next_url": target, "first": True})
        if pending:
            record_access(request, AccessLog.Event.OTP_FAILED, user.get_username(), user)
        form.add_error("code", "Codice non valido: inquadra di nuovo il QR code e controlla l'ora del telefono.")
    uri = twofactor.provisioning_uri(secret, user.get_username())
    return render(request, "accounts/otp_setup.html", {
        "form": form, "qr": twofactor.qr_svg(uri), "secret": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
        "pending": pending, "required": twofactor.role_requires(user),
    })


def security(request):
    """Il mio profilo › Verifica in due passaggi."""
    user = request.user
    enrolled = twofactor.is_enrolled(user)
    form = OTPForm(request.POST or None)
    if request.method == "POST" and enrolled and form.is_valid():
        if not twofactor.verify(user, form.cleaned_data["code"]):
            form.add_error("code", "Codice non valido o già usato.")
        elif request.POST.get("action") == "codes":
            return render(request, "accounts/otp_codes.html", {
                "codes": twofactor.regenerate_recovery_codes(user), "next_url": reverse("accounts:security")})
        elif request.POST.get("action") == "disable" and not twofactor.role_requires(user):
            twofactor.disable(user, by=user)
            messages.success(request, "Verifica in due passaggi disattivata.")
            return redirect("accounts:security")
    return render(request, "accounts/security.html", {
        "enrolled": enrolled, "device": getattr(user, "two_factor", None) if enrolled else None,
        "codes_left": twofactor.recovery_codes_left(user) if enrolled else 0,
        "required": twofactor.role_requires(user), "form": form,
    })


@require_POST
def user_reset_2fa(request, pk):
    """L'amministratore reimposta la verifica di chi ha perso il telefono: al prossimo accesso la riattiva."""
    if not request.user.has_perm("accounts.change_user"):
        return redirect("core:dashboard")
    target = get_object_or_404(User, pk=pk)
    if twofactor.disable(target, by=request.user):
        messages.success(request, f"Verifica in due passaggi di {target} reimpostata: la riattiverà al prossimo accesso.")
    else:
        messages.info(request, f"{target} non aveva la verifica in due passaggi attiva.")
    return redirect("accounts:user_list")


class LogoutView(auth_views.LogoutView):
    pass


class ProfileView(FormPageMixin, UpdateView):
    form_class = ProfileForm
    page_title = "Il mio profilo"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profilo aggiornato.")
        return super().form_valid(form)


class PasswordChangeView(FormPageMixin, auth_views.PasswordChangeView):
    page_title = "Cambia password"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, "Password aggiornata.")
        return super().form_valid(form)


class UserListView(PermRequiredMixin, ListView):
    permission_required = "accounts.view_user"
    template_name = "accounts/user_list.html"
    paginate_by = 50

    def get_queryset(self):
        qs = User.objects.select_related("two_factor").order_by("-is_active", "last_name", "first_name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        if role := self.request.GET.get("role"):
            qs = qs.filter(role=role)
        return qs


class UserCreateView(PermRequiredMixin, FormPageMixin, CreateView):
    permission_required = "accounts.add_user"
    form_class = UserCreateForm
    page_title = "Nuovo utente"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        messages.success(self.request, "Utente creato.")
        return super().form_valid(form)


class UserUpdateView(PermRequiredMixin, FormPageMixin, UpdateView):
    permission_required = "accounts.change_user"
    model = User
    form_class = UserForm
    success_url = reverse_lazy("accounts:user_list")

    def get_page_title(self):
        return f"Modifica utente {self.object}"

    def form_valid(self, form):
        if form.instance == self.request.user and not form.cleaned_data["is_active"]:
            form.add_error("is_active", "Non puoi disattivare il tuo stesso utente.")
            return self.form_invalid(form)
        messages.success(self.request, "Utente aggiornato.")
        return super().form_valid(form)


def user_set_password(request, pk):
    if not request.user.has_perm("accounts.change_user"):
        return redirect("core:dashboard")
    target = get_object_or_404(User, pk=pk)
    form = AdminSetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_event(AuditLog.Action.PERMISSION, target, changes={"password": ["***", "reimpostata"]})
        messages.success(request, f"Password di {target} reimpostata.")
        return redirect("accounts:user_list")
    return render(request, "generic/form.html", {"form": form, "page_title": f"Reimposta password di {target}",
                                                 "submit_label": "Reimposta", "cancel_url": reverse("accounts:user_list")})


def user_permissions(request, pk):
    """Permessi granulari: per ogni permesso si vede il default del ruolo e si può concedere o negare."""
    if not request.user.has_perm("accounts.change_user"):
        return redirect("core:dashboard")
    target = get_object_or_404(User, pk=pk)
    role_perms = set(
        Permission.objects.filter(group__user=target).values_list("pk", flat=True)
    )
    overrides = {o.permission_id: o for o in target.permission_overrides.all()}
    permissions = (
        Permission.objects.filter(content_type__app_label__in=MANAGED_APPS)
        .select_related("content_type")
        .order_by("content_type__app_label", "content_type__model", "codename")
    )

    if request.method == "POST":
        for perm in permissions:
            value = request.POST.get(f"perm_{perm.pk}", "role")
            existing = overrides.get(perm.pk)
            if value == "role":
                if existing:
                    existing.delete()
            else:
                allow = value == "allow"
                if existing is None:
                    UserPermissionOverride.objects.create(user=target, permission=perm, allow=allow)
                elif existing.allow != allow:
                    existing.allow = allow
                    existing.save()
        target.clear_permission_cache()
        messages.success(request, f"Permessi di {target} aggiornati.")
        return redirect("accounts:user_permissions", pk=target.pk)

    grouped = OrderedDict()
    for perm in permissions:
        model_class = perm.content_type.model_class()
        section = model_class._meta.verbose_name_plural.capitalize() if model_class else perm.content_type.model
        override = overrides.get(perm.pk)
        grouped.setdefault(section, []).append({
            "perm": perm,
            "role_default": perm.pk in role_perms,
            "state": "role" if override is None else ("allow" if override.allow else "deny"),
        })
    return render(request, "accounts/user_permissions.html", {"target": target, "grouped": grouped})


class AccessLogListView(PermRequiredMixin, ListView):
    permission_required = "accounts.view_accesslog"
    template_name = "accounts/accesslog_list.html"
    paginate_by = 100

    def get_queryset(self):
        qs = AccessLog.objects.select_related("user")
        params = self.request.GET
        if params.get("username"):
            qs = qs.filter(username__icontains=params["username"])
        if params.get("event"):
            qs = qs.filter(event=params["event"])
        if params.get("ip"):
            qs = qs.filter(ip_address__startswith=params["ip"])
        if params.get("date_from"):
            qs = qs.filter(timestamp__date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(timestamp__date__lte=params["date_to"])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["events"] = AccessLog.Event.choices
        return context


def set_theme(request):
    """Cambio rapido del tema (chiaro / scuro / automatico) dalla barra superiore."""
    if request.method == "POST" and request.POST.get("theme") in User.Theme.values:
        request.user.theme = request.POST["theme"]
        request.user.save(update_fields=["theme"])
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = reverse("core:dashboard")
    return redirect(target)
