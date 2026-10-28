from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import FormView

from fasas.audit.context import audit_context

from .locking import creation_decision, edit_decision


class PermRequiredMixin(PermissionRequiredMixin):
    raise_exception = True


class GuestMixin:
    """Recupera l'ospite dall'URL (guest_pk) e lo mette nel contesto."""

    guest_url_kwarg = "guest_pk"

    def get_guest(self):
        from fasas.guests.models import Guest

        if not hasattr(self, "_guest"):
            self._guest = get_object_or_404(Guest, pk=self.kwargs[self.guest_url_kwarg])
        return self._guest

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["guest"] = self.get_guest()
        return context


class FormPageMixin:
    """Valori usati dal template generico generic/form.html."""

    page_title = ""
    submit_label = "Salva"
    template_name = "generic/form.html"

    def get_page_title(self):
        return self.page_title

    def get_cancel_url(self):
        return self.request.GET.get("next") or getattr(self, "cancel_url", None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("page_title", self.get_page_title())
        context.setdefault("submit_label", self.submit_label)
        context.setdefault("cancel_url", self.get_cancel_url())
        return context


class RecordCreateMixin(GuestMixin, FormPageMixin):
    """Creazione di una registrazione su un ospite: rifiuta turni chiusi e cartelle archiviate."""

    def form_valid(self, form):
        guest = self.get_guest()
        occurred_at = form.cleaned_data.get("occurred_at") or getattr(form.instance, "occurred_at", None)
        decision = creation_decision(guest, occurred_at, self.request.user)
        if not decision.allowed:
            form.add_error(None, decision.message)
            return self.form_invalid(form)
        form.instance.guest = guest
        response = super().form_valid(form)
        messages.success(self.request, "Registrazione salvata.")
        return response

    def get_success_url(self):
        return self.get_guest().get_absolute_url()


class LockedUpdateMixin(FormPageMixin):
    """
    Modifica di un dato sanitario secondo le regole di blocco: se oltre la finestra
    di modifica il form chiede la motivazione, che finisce nell'audit log.
    """

    reason_field = "edit_reason"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.decision = edit_decision(self.object, request.user)
        if not self.decision.allowed:
            messages.error(request, self.decision.message)
            return redirect(self.get_locked_redirect_url())
        return super().dispatch(request, *args, **kwargs)

    def get_locked_redirect_url(self):
        guest = getattr(self.object, "guest", None)
        return guest.get_absolute_url() if guest else "/"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.decision.reason_required:
            form.fields[self.reason_field] = forms.CharField(
                label="Motivazione della modifica", widget=forms.Textarea(attrs={"rows": 2}), required=True
            )
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["decision"] = self.decision
        return context

    def form_valid(self, form):
        reason = form.cleaned_data.get(self.reason_field, "")
        with audit_context(reason=reason):
            response = super().form_valid(form)
        messages.success(self.request, "Modifica salvata e registrata nell'audit log.")
        return response


class VoidForm(forms.Form):
    reason = forms.CharField(label="Motivo dell'annullamento", widget=forms.Textarea(attrs={"rows": 3}))


class VoidRecordView(PermRequiredMixin, FormPageMixin, FormView):
    """Annullamento (mai cancellazione fisica) di una registrazione clinica."""

    model = None
    form_class = VoidForm
    submit_label = "Annulla registrazione"

    def get_permission_required(self):
        return [f"{self.model._meta.app_label}.delete_{self.model._meta.model_name}"]

    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(self.model.objects, pk=kwargs["pk"])
        decision = edit_decision(self.object, request.user)
        if not decision.allowed:
            raise PermissionDenied(decision.message)
        return super().dispatch(request, *args, **kwargs)

    def get_page_title(self):
        return f"Annulla: {self.object}"

    def form_valid(self, form):
        self.object.void(self.request.user, form.cleaned_data["reason"])
        messages.success(self.request, "Registrazione annullata. Resta visibile nello storico e nell'audit.")
        return redirect(self.object.guest.get_absolute_url())
