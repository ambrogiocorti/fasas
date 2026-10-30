"""
Viste CRUD generiche per le tabelle di configurazione (farmaci, tipi parametro, tag, protocolli...).
Le registrazioni cliniche hanno invece viste dedicate con le regole di blocco.
"""
from django.contrib import messages
from django.urls import path, reverse
from django.views.generic import CreateView, ListView, UpdateView

from .views_mixins import FormPageMixin, PermRequiredMixin


def _display(obj, field):
    value = getattr(obj, f"get_{field}_display", None)
    if callable(value):
        return value()
    value = getattr(obj, field)
    if callable(value):
        value = value()
    if isinstance(value, bool):
        return "✔" if value else "—"
    return "" if value is None else value


class ConfigListView(PermRequiredMixin, ListView):
    template_name = "generic/list.html"
    list_display = ()
    search_fields = ()
    url_prefix = ""
    page_title = ""
    paginate_by = 100

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q and self.search_fields:
            from django.db.models import Q

            cond = Q()
            for field in self.search_fields:
                cond |= Q(**{f"{field}__icontains": q})
            qs = qs.filter(cond)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meta = self.model._meta
        context.update({
            "page_title": self.page_title or meta.verbose_name_plural.capitalize(),
            "headers": [meta.get_field(f).verbose_name if f in {x.name for x in meta.get_fields()} else f
                        for f in self.list_display],
            "rows": [
                {"obj": obj, "cells": [_display(obj, f) for f in self.list_display],
                 "edit_url": reverse(f"{self.url_prefix}_update", args=[obj.pk]),
                 # azione aggiuntiva della riga (es. «Valida»), se il modello la prevede per questo utente
                 "action": obj.row_action(self.request.user) if hasattr(obj, "row_action") else None}
                for obj in context["object_list"]
            ],
            "create_url": reverse(f"{self.url_prefix}_create"),
            "can_add": self.request.user.has_perm(f"{meta.app_label}.add_{meta.model_name}"),
            "can_change": self.request.user.has_perm(f"{meta.app_label}.change_{meta.model_name}"),
            "searchable": bool(self.search_fields),
        })
        return context


class ConfigCreateView(PermRequiredMixin, FormPageMixin, CreateView):
    url_prefix = ""

    def get_page_title(self):
        return f"Nuovo: {self.model._meta.verbose_name}"

    def get_success_url(self):
        messages.success(self.request, "Salvato.")
        return reverse(f"{self.url_prefix}_list")

    def get_cancel_url(self):
        return reverse(f"{self.url_prefix}_list")


class ConfigUpdateView(PermRequiredMixin, FormPageMixin, UpdateView):
    url_prefix = ""

    def get_page_title(self):
        return f"Modifica {self.model._meta.verbose_name}: {self.object}"

    def get_success_url(self):
        messages.success(self.request, "Modifiche salvate.")
        return reverse(f"{self.url_prefix}_list")

    def get_cancel_url(self):
        return reverse(f"{self.url_prefix}_list")


def config_urls(slug, name, model, form_class, list_display, app_label=None, search_fields=(), queryset=None,
                namespace=None):
    """Genera le tre URL (elenco, nuovo, modifica) per una tabella di configurazione."""
    meta = model._meta
    prefix = f"{namespace}:{name}" if namespace else name
    perms = lambda action: [f"{meta.app_label}.{action}_{meta.model_name}"]  # noqa: E731
    common = {"model": model, "url_prefix": prefix}
    if queryset is not None:
        common["queryset"] = queryset
    return [
        path(f"{slug}/", ConfigListView.as_view(
            permission_required=perms("view"), list_display=list_display, search_fields=search_fields, **common
        ), name=f"{name}_list"),
        path(f"{slug}/nuovo/", ConfigCreateView.as_view(
            permission_required=perms("add"), form_class=form_class, **common
        ), name=f"{name}_create"),
        path(f"{slug}/<int:pk>/", ConfigUpdateView.as_view(
            permission_required=perms("change"), form_class=form_class, **common
        ), name=f"{name}_update"),
    ]
