from fasas.core.middleware import client_ip

from .context import audit_context


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        with audit_context(user=user, ip=client_ip(request), reason="", source="web"):
            return self.get_response(request)
