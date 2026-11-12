"""
Un utente «Familiare o tutore» vede solo l'area familiari: profilo, password, notifiche e le pagine del proprio
collegamento. Qualunque altra pagina (anche una senza permessi specifici) lo riporta all'area familiari.
"""
from django.shortcuts import redirect

ALLOWED_NAMESPACES = {"families"}
ALLOWED = {
    "core:dashboard", "core:settings",
    "accounts:login", "accounts:logout", "accounts:otp_verify", "accounts:otp_setup", "accounts:security",
    "accounts:profile", "accounts:set_theme", "accounts:password_change",
    "notifications:list", "notifications:count", "notifications:mark_read", "notifications:mark_all_read",
    "notifications:open", "notifications:devices", "notifications:push_subscribe", "notifications:push_unsubscribe",
    "notifications:push_test", "modulistica:family_fill", "modulistica:family_pdf",
}
ALLOWED_NAMES = {"service_worker", "manifest", "favicon"}


class FamilyScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or getattr(user, "role", "") != "family" or user.is_superuser:
            return None
        match = request.resolver_match
        if match is None:
            return None
        if match.namespace in ALLOWED_NAMESPACES or match.view_name in ALLOWED or (
                not match.namespace and match.url_name in ALLOWED_NAMES):
            return None
        return redirect("families:home")
