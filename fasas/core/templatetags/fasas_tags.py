from django import template
from django.utils.html import format_html

register = template.Library()

STATE_ICONS = {"ok": ("check", "ok", "completato"), "missing": ("alert", "warn", "mancante"),
               "na": ("minus", "muted", "non applicabile")}


@register.simple_tag
def state_icon(state):
    name, css, label = STATE_ICONS.get(state, ("info", "muted", state))
    return format_html(
        '<span class="state state-{}" title="{}" role="img" aria-label="{}">'
        '<svg class="icon" aria-hidden="true"><use href="#i-{}"></use></svg></span>', css, label, label, name)


@register.filter
def has_perm(user, perm):
    return user.has_perm(perm)


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag
def tag_chip(tag):
    return format_html('<span class="chip" style="--chip:{}">{}</span>', tag.color, tag.name)


@register.filter
def level_class(level):
    return {"critical": "danger", "warning": "warn", "info": "info", "danger": "danger"}.get(level, "info")


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Querystring corrente con alcuni parametri sostituiti."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return "?" + params.urlencode() if params else "?"


@register.filter
def percent(part, total):
    try:
        return int(round(100 * part / total)) if total else 0
    except (TypeError, ZeroDivisionError):
        return 0


@register.simple_tag
def icon(name, css=""):
    """Icona SVG dallo sprite in partials/icons.html."""
    return format_html('<svg class="icon {}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', css, name)
