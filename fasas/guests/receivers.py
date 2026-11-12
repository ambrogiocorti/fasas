from fasas.audit.models import AuditLog
from fasas.audit.services import log_event


def tags_changed(sender, instance, action, pk_set, **kwargs):
    """I tag clinici sono una relazione molti-a-molti: post_save non li vede, si tracciano qui."""
    from .models import ClinicalTag, Guest

    if action not in ("post_add", "post_remove") or not pk_set or not isinstance(instance, Guest):
        return
    names = ", ".join(ClinicalTag.objects.filter(pk__in=pk_set).values_list("name", flat=True))
    change = [None, names] if action == "post_add" else [names, None]
    log_event(AuditLog.Action.UPDATE, instance, changes={"tag clinici": change})
