from django.db import migrations

from fasas.core.db import append_only_operations

forwards, backwards = append_only_operations("accounts_accesslog")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(forwards, backwards)]
