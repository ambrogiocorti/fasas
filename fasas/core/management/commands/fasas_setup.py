"""
Inizializzazione (idempotente) del sistema: ruoli e permessi, comunità, configurazione,
parametri sanitari, protocolli, checklist di turno, impostazioni notifiche.
Va eseguito dopo ogni "migrate".
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from fasas.audit.context import audit_context

PARAMETER_TYPES = [
    # codice, nome, unità, tipo, min, max, min2, max2, decimali
    ("temperatura", "Temperatura", "°C", "single", "36.0", "37.4", None, None, 1),
    ("pressione", "Pressione arteriosa", "mmHg", "bp", "90", "140", "60", "90", 0),
    ("glicemia", "Glicemia", "mg/dL", "single", "70", "180", None, None, 0),
    ("peso", "Peso", "kg", "single", None, None, None, None, 1),
    ("saturazione", "Saturazione O2", "%", "single", "94", "100", None, None, 0),
    ("frequenza", "Frequenza cardiaca", "bpm", "single", "60", "100", None, None, 0),
    ("dolore", "Dolore (scala NRS/PAINAD)", "punti", "single", "0", "3", None, None, 0),
]

PROTOCOLS = [
    ("Protocollo evacuazione", "evacuation", {"days": 3},
     "Somministrare il lassativo previsto dalla prescrizione\nSe nessun risultato entro 12 ore: eseguire lavanda intestinale\n"
     "Informare il medico curante se persiste", "warning"),
    ("Protocollo febbre", "fever", {"threshold": 37.5, "parameter": "temperatura"},
     "Ricontrollare la temperatura dopo 30 minuti\nSomministrare l'antipiretico SOS se prescritto\n"
     "Idratare l'ospite\nAvvisare il medico se > 38.5 °C o persistente oltre 24 ore", "warning"),
    ("Protocollo glicemia", "glycemia", {"min": 70, "max": 250, "parameter": "glicemia"},
     "Ipoglicemia: somministrare zuccheri semplici e ricontrollare dopo 15 minuti\n"
     "Iperglicemia: ricontrollare e applicare lo schema insulinico prescritto\nAvvisare il medico", "critical"),
    ("Protocollo crisi epilettica", "seizure", {"min_duration_minutes": 0},
     "Proteggere l'ospite da traumi e posizionarlo in sicurezza\nCronometrare la durata della crisi\n"
     "Se la crisi supera la durata indicata in prescrizione: somministrare il farmaco SOS antiepilettico\n"
     "Chiamare il 112/118 se la crisi non cede\nAvvisare medico e familiari/tutore", "critical"),
    ("Protocollo agitazione", "agitation", {"events": 2, "window_hours": 24},
     "Applicare le strategie di contenimento relazionale previste dal PAI\nValutare il farmaco SOS se prescritto\n"
     "Informare il coordinatore", "warning"),
    ("Protocollo farmaci SOS", "sos", {"count": 2, "window_hours": 24},
     "Verificare la corretta indicazione delle somministrazioni SOS\nInformare il medico per rivalutazione terapia",
     "warning"),
]

CHECKLISTS = {
    "M": ("Checklist turno mattina", [
        ("Farmaci del mattino somministrati", "therapy", "", None),
        ("Igiene personale", "hygiene", "", None),
        ("Colazione", "meal", "breakfast", None),
        ("Pranzo", "meal", "lunch", None),
        ("Parametri sanitari", "parameters", "", None),
        ("Evacuazione registrata", "evacuation", "", None),
    ]),
    "P": ("Checklist turno pomeriggio", [
        ("Farmaci del pomeriggio somministrati", "therapy", "", None),
        ("Merenda", "meal", "snack", None),
        ("Cena", "meal", "dinner", None),
        ("Attività del pomeriggio registrate", "manual", "", None),
    ]),
    "N": ("Checklist turno notte", [
        ("Farmaci serali e notturni somministrati", "therapy", "", None),
        ("Controlli notturni effettuati", "manual", "", None),
        ("Consegne scritte al turno del mattino", "manual", "", None),
    ]),
}


class Command(BaseCommand):
    help = "Inizializza ruoli, permessi e configurazioni predefinite (idempotente)"

    def add_arguments(self, parser):
        parser.add_argument("--community", default="", help="Nome della comunità")

    def handle(self, *args, **options):
        with audit_context(source="setup"):
            self._setup(options)

    def _setup(self, options):
        from fasas.accounts.roles import setup_role_groups
        from fasas.clinical.models import ParameterType
        from fasas.core.models import Community, SystemConfig
        from fasas.daily.models import ChecklistItem, ChecklistTemplate
        from fasas.notifications.services import ensure_default_settings
        from fasas.protocols.models import Protocol

        community = Community.default()
        if options["community"]:
            community.name = options["community"]
            community.save()
        SystemConfig.get()
        self.stdout.write(f"Comunità: {community}")

        setup_role_groups(self.stdout)
        self.stdout.write("Ruoli e permessi aggiornati")

        for order, (code, name, unit, kind, lo, hi, lo2, hi2, dec) in enumerate(PARAMETER_TYPES):
            ParameterType.objects.get_or_create(code=code, defaults={
                "name": name, "unit": unit, "kind": kind, "decimals": dec, "order": order,
                "min_normal": Decimal(lo) if lo else None, "max_normal": Decimal(hi) if hi else None,
                "min_normal_2": Decimal(lo2) if lo2 else None, "max_normal_2": Decimal(hi2) if hi2 else None,
            })
        self.stdout.write("Tipi di parametro sanitario presenti")

        for name, kind, params, actions, severity in PROTOCOLS:
            Protocol.objects.get_or_create(kind=kind, name=name, defaults={
                "params": params, "actions": actions, "severity": severity,
                "description": "Protocollo di esempio: da validare dal medico / direttore sanitario della struttura.",
            })
        self.stdout.write("Protocolli predefiniti presenti (da validare clinicamente)")

        for shift, (name, items) in CHECKLISTS.items():
            template, created = ChecklistTemplate.objects.get_or_create(shift=shift, name=name)
            if created:
                for order, (label, check_type, meal, _) in enumerate(items):
                    ChecklistItem.objects.create(template=template, label=label, check_type=check_type, meal=meal,
                                                 order=order)
        self.stdout.write("Checklist di turno presenti")

        ensure_default_settings()
        self.stdout.write(self.style.SUCCESS("Setup completato."))
