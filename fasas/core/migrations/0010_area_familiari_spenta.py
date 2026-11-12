"""Area familiari: modulo spento di default, anche nelle installazioni esistenti (si accende dopo il parere del DPO)."""
import fasas.core.models
from django.db import migrations, models


def switch_off_families(apps, schema_editor):
    SystemConfig = apps.get_model("core", "SystemConfig")
    for config in SystemConfig.objects.all():
        disabled = list(config.disabled_modules or [])
        if "families" not in disabled:
            config.disabled_modules = disabled + ["families"]
            config.save(update_fields=["disabled_modules"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_moduli_accendibili"),
    ]

    operations = [
        migrations.AlterField(
            model_name="systemconfig",
            name="disabled_modules",
            field=models.JSONField(
                blank=True,
                default=fasas.core.models.default_disabled_modules,
                verbose_name="moduli spenti",
            ),
        ),
        migrations.RunPython(switch_off_families, migrations.RunPython.noop),
    ]
