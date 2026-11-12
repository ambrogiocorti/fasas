"""Tipi di scadenza proposti alla prima installazione (modificabili; periodicità da confermare con l'RSPP)."""
from django.db import migrations

TYPES = [
    ("Sicurezza dei lavoratori (formazione generale e specifica)", "training", 60, ["operator", "coordinator"],
     "D.Lgs. 81/2008 art. 37; aggiornamento quinquennale (Accordo Stato-Regioni)"),
    ("BLSD (rianimazione e defibrillatore)", "training", 24, ["operator", "coordinator"],
     "Retraining periodico secondo l'ente formatore accreditato"),
    ("Antincendio (addetto designato)", "training", 60, [], "D.M. 2/9/2021: aggiornamento almeno quinquennale"),
    ("Primo soccorso (addetto designato)", "training", 36, [], "D.M. 388/2003: aggiornamento triennale"),
    ("Preposto alla sicurezza", "training", 24, ["coordinator"], "D.Lgs. 81/2008 art. 37 c. 7-ter: almeno biennale"),
    ("HACCP (alimentarista)", "training", None, [], "Periodicità della normativa regionale e del piano di autocontrollo"),
    ("Idoneità alla mansione (medico competente)", "fitness", None, ["operator", "coordinator"],
     "D.Lgs. 81/2008 art. 41: scadenza indicata nel giudizio di idoneità"),
]


def create_types(apps, schema_editor):
    CredentialType = apps.get_model("staffing", "CredentialType")
    for order, (name, category, months, roles, reference) in enumerate(TYPES):
        CredentialType.objects.get_or_create(name=name, defaults={
            "category": category, "validity_months": months, "roles": roles, "reference": reference,
            "order": order * 10})


class Migration(migrations.Migration):
    dependencies = [("staffing", "0002_scadenze_del_personale")]

    operations = [migrations.RunPython(create_types, migrations.RunPython.noop)]
