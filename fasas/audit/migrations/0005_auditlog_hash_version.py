from django.db import migrations, models


class Migration(migrations.Migration):
    """Le voci esistenti restano alla versione 1 dell'impronta; le nuove usano la 2 (vedi HASH_VERSION)."""

    dependencies = [("audit", "0004_punti_di_controllo")]

    operations = [
        migrations.AddField(model_name="auditlog", name="hash_version",
                            field=models.PositiveSmallIntegerField(default=1)),
        migrations.AlterField(model_name="auditlog", name="hash_version",
                              field=models.PositiveSmallIntegerField(default=2)),
    ]
