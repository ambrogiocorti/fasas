from django.db import migrations

from fasas.core.db import append_only_operations

forwards, backwards = append_only_operations("audit_auditlog")


class Migration(migrations.Migration):
    """Su PostgreSQL il database stesso rifiuta UPDATE, DELETE e TRUNCATE sull'audit log."""

    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunPython(forwards, backwards)]
