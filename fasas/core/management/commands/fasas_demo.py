"""
Dati dimostrativi per provare il sistema: utenti per ogni ruolo, ospiti di fantasia,
farmaci, terapie, parametri, eventi, PAI. Da NON usare in produzione.
"""
import datetime
import random
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from fasas.audit.context import audit_context

DEMO_PASSWORD = "Demo-Fasas-2026!"


def demo_password():
    """Password degli utenti di prova: quella pubblica, o FASAS_PRESENTAZIONE_PASSWORD per una presentazione online."""
    import os

    return os.environ.get("FASAS_PRESENTAZIONE_PASSWORD", "").strip() or DEMO_PASSWORD

USERS = [
    ("admin", "Anna", "Amministratrice", "admin", ""),
    ("coordinatore", "Carlo", "Coordinatore", "coordinator", "Infermiere"),
    ("operatore", "Olga", "Operatrice", "operator", "OSS"),
    ("medico", "Marta", "Medico", "doctor", "Medico di struttura"),
    ("amministrativo", "Paolo", "Amministrativo", "administrative", "Ufficio amministrativo"),
    ("familiare", "Elena", "Rossi", "family", "Sorella di Mario Rossi, amministratrice di sostegno"),
]

GUESTS = [
    ("Mario", "Rossi", "M", datetime.date(1978, 3, 12), "RSSMRA78C12F205X", "1A", ["Epilettico", "Rischio caduta"]),
    ("Giulia", "Bianchi", "F", datetime.date(1985, 7, 2), "BNCGLI85L42H501Y", "1B", ["Disfagia"]),
    ("Luca", "Verdi", "M", datetime.date(1969, 11, 25), "VRDLCU69S25L219Z", "2A", ["Diabetico"]),
    ("Sara", "Neri", "F", datetime.date(1992, 1, 18), "NRESRA92A58D612W", "2B", []),
]

TAGS = [
    ("Diabetico", "#b45309", "Controllare la glicemia prima dei pasti principali", []),
    ("Epilettico", "#7c3aed", "Tenere a portata di mano il farmaco SOS antiepilettico", ["seizure"]),
    ("Disfagia", "#0e7490", "Dieta a consistenza modificata – acqua gelificata", []),
    ("Rischio caduta", "#be123c", "Accompagnare negli spostamenti", ["fall"]),
]

DRUGS = [
    ("Depakin Chrono", "acido valproico", "N03AG01", "tablet", "500 mg", "compresse", 30),
    ("Keppra", "levetiracetam", "N03AX14", "tablet", "500 mg", "compresse", 30),
    ("Buccolam", "midazolam", "N05CD08", "vial", "10 mg", "siringhe", 2),
    ("Tachipirina", "paracetamolo", "N02BE01", "tablet", "500 mg", "compresse", 20),
    ("Metformina", "metformina", "A10BA02", "tablet", "850 mg", "compresse", 30),
    ("Movicol", "macrogol", "A06AD65", "sachet", "13,8 g", "bustine", 10),
    ("Coumadin", "warfarin", "B01AA03", "tablet", "5 mg", "compresse", 10),
    ("Cardioaspirin", "acido acetilsalicilico", "B01AC06", "tablet", "100 mg", "compresse", 10),
]


class Command(BaseCommand):
    help = "Crea dati dimostrativi (utenti, ospiti fittizi, terapie). Solo per ambienti di prova."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Esegue anche se esistono già ospiti")
        parser.add_argument("--skip-if-exists", action="store_true",
                            help="Se esistono già ospiti non fa nulla (usato dagli script di avvio)")
        parser.add_argument("--ambiente-di-prova", action="store_true",
                            help="Conferma che è un'installazione di prova anche se DEBUG è spento (es. container di prova)")

    def handle(self, *args, **options):
        from fasas.guests.models import Guest

        if not settings.DEBUG and not options["ambiente_di_prova"]:
            # Gli utenti demo hanno password pubblicate nel README: su un'installazione vera sarebbero una porta aperta
            raise CommandError("I dati demo creano utenti (anche un amministratore) con password pubbliche: si usano "
                               "solo nelle installazioni di prova. Su un'installazione di prova con DEBUG spento "
                               "aggiungere --ambiente-di-prova; MAI dove ci sono o ci saranno dati reali.")

        if Guest.objects.exists() and options["skip_if_exists"]:
            from fasas.accounts.models import User

            if User.objects.filter(username="admin", email="admin@example.invalid").exists():
                # Database di prova creato da una versione precedente: si aggiungono solo le novità della demo
                call_command("fasas_setup", stdout=self.stdout)
                with audit_context(source="demo"):
                    users = self._users()
                    self._billing(users)
                    self._rota(users)
                    self._novita(users)
            self.stdout.write("Dati presenti: i dati demo non vengono ricaricati.")
            return
        if Guest.objects.exists() and not options["force"]:
            raise CommandError("Esistono già ospiti: usare --force per aggiungere comunque i dati demo.")
        call_command("fasas_setup", stdout=self.stdout)
        with audit_context(source="demo"):
            self._create()
        self.stdout.write(self.style.SUCCESS(
            f"Dati demo creati. Utenti: {', '.join(u[0] for u in USERS)} – password: "
            f"{DEMO_PASSWORD if demo_password() == DEMO_PASSWORD else '(quella di FASAS_PRESENTAZIONE_PASSWORD)'}"
        ))

    def _create(self):
        from fasas.guests.models import ClinicalTag
        from fasas.pharmacy.models import Drug, DrugInteraction

        users = self._users()

        tags = {}
        for name, color, alert, escalate in TAGS:
            tags[name], _ = ClinicalTag.objects.get_or_create(name=name, defaults={
                "color": color, "alert_message": alert, "escalate_event_types": escalate})

        drugs = {}
        for name, ingredient, atc, form, strength, unit, minimum in DRUGS:
            drugs[ingredient], _ = Drug.objects.get_or_create(name=name, defaults={
                "active_ingredient": ingredient, "atc_code": atc, "form": form, "strength": strength,
                "stock_unit": unit, "min_stock": Decimal(minimum)})
        DrugInteraction.objects.get_or_create(
            ingredient_a="warfarin", ingredient_b="acido acetilsalicilico",
            defaults={"severity": "major", "description": "Aumento del rischio emorragico: associazione da valutare dal medico.",
                      "source": "Esempio dimostrativo – verificare su fonti ufficiali (AIFA / scheda tecnica)"})
        # Demo: il medico di fantasia «valida» protocolli e interazione e si attivano tutti i promemoria,
        # così si vede come funzionano. In una comunità reale lo fa il medico della struttura.
        from django.utils import timezone

        from fasas.core.models import SystemConfig
        from fasas.protocols.models import Protocol

        DrugInteraction.objects.filter(validated_at=None).update(validated_by=users["doctor"], validated_at=timezone.now())
        Protocol.objects.filter(validated_at=None).update(
            validated_by_user=users["doctor"], validated_by=str(users["doctor"]), validated_at=timezone.now())
        SystemConfig.objects.update(therapy_check_interactions=True)

        coordinator = users["coordinator"]
        with audit_context(user=users["operator"]):
            self._populate(users, tags, drugs, coordinator)

    def _users(self):
        from fasas.accounts.models import User

        users = {}
        for username, first, last, role, qualification in USERS:
            user, created = User.objects.get_or_create(username=username, defaults={
                "first_name": first, "last_name": last, "role": role, "qualification": qualification,
                "email": f"{username}@example.invalid",
            })
            if created:
                user.set_password(demo_password())
                user.save()
            users[role] = user
        return users

    def _rota(self, users):
        """Calendario turni dimostrativo: ciclo di 7 giorni sfalsato tra gli operatori, mese corrente pubblicato."""
        from fasas.accounts.models import User
        from fasas.billing.services import month_days, month_start, shift_month
        from fasas.staffing.models import LeaveRequest, RotaEntry
        from fasas.staffing.services import publish, staff

        if RotaEntry.objects.exists():
            return
        for username, first, last in [("operatore2", "Luca", "Bassi"), ("operatore3", "Sofia", "Galli"),
                                      ("operatore4", "Marco", "Conti"), ("operatore5", "Irene", "Fabbri")]:
            user, created = User.objects.get_or_create(username=username, defaults={
                "first_name": first, "last_name": last, "role": "operator", "qualification": "OSS",
                "email": f"{username}@example.invalid"})
            if created:
                user.set_password(demo_password())
                user.save()
        cycle = ["M", "M", "P", "P", "N", "R", "R"]
        current = month_start()
        people = [u for u, _ in staff()]
        with audit_context(user=users["coordinator"]):
            for first in (current, shift_month(current, 1)):
                for day in month_days(first):
                    for offset, user in enumerate(people):
                        code = cycle[(day.toordinal() + offset * 2) % len(cycle)]
                        RotaEntry.objects.create(user=user, date=day, code=code,
                                                 is_lead=user.role == "coordinator" and code in ("M", "P"))
            publish(current, users["coordinator"], "Calendario dimostrativo")
            nxt = shift_month(current, 1)
            LeaveRequest.objects.create(user=users["operator"], kind="F", start=nxt.replace(day=10),
                                        end=nxt.replace(day=14), note="Ferie programmate (demo)")

    def _billing(self, users):
        """Rette di esempio e qualche movimento nel mese precedente, per provare presenze e prospetti."""
        from fasas.billing.models import BillingSettings, GuestFeeLine
        from fasas.billing.services import month_start, shift_month
        from fasas.guests.models import AdmissionEvent, Guest

        if GuestFeeLine.objects.exists():
            return
        settings = BillingSettings.get()
        if not settings.payee_name:
            settings.payee_name = "Cooperativa Sociale Esempio (dati di fantasia)"
            settings.payee_tax_code = "00000000000"
            settings.iban = "IT00X0000000000000000000000"
            settings.save()
        previous = shift_month(month_start(), -1)
        with audit_context(user=users["administrative"]):
            for guest in Guest.objects.filter(fiscal_code__in=[g[4] for g in GUESTS]):
                start = guest.admission_date
                GuestFeeLine.objects.create(guest=guest, description="Quota sanitaria", payer="region",
                                            payer_name="ATS di esempio", daily_rate=Decimal("78.50"), valid_from=start)
                GuestFeeLine.objects.create(guest=guest, description="Quota sociale", payer="municipality",
                                            payer_name="Comune di Milano", daily_rate=Decimal("42.00"),
                                            hospital_percent=70, family_percent=70, absent_percent=70, valid_from=start)
                GuestFeeLine.objects.create(guest=guest, description="Compartecipazione", payer="guest",
                                            payer_name=f"Elena {guest.last_name} (amministratore di sostegno)",
                                            daily_rate=Decimal("15.00"), hospital_percent=100, family_percent=100,
                                            absent_percent=100, max_absence_days=20, valid_from=start)
        with audit_context(user=users["coordinator"]):
            for cf, moves in [("VRDLCU69S25L219Z", [("hospitalization", 8), ("return", 14)]),
                              ("BNCGLI85L42H501Y", [("absence", 20), ("return", 23)])]:
                guest = Guest.objects.filter(fiscal_code=cf).first()
                if guest and not guest.admission_events.filter(date__gte=previous, date__lt=month_start()).exists():
                    for kind, day in moves:
                        AdmissionEvent.objects.create(guest=guest, kind=kind, date=previous.replace(day=day),
                                                      notes="Movimento dimostrativo")

    def _populate(self, users, tags, drugs, coordinator):
        from fasas.appointments.models import Appointment
        from fasas.clinical.models import ClinicalEvent, ParameterReading, ParameterType, Therapy
        from fasas.core.models import Community
        from fasas.daily.models import DiaryEntry, EvacuationRecord
        from fasas.guests.models import AdmissionEvent, Allergy, Diagnosis, Guest, GuestContact
        from fasas.pai.models import PAI, PAIGoal
        from fasas.pharmacy.services import load_lot

        today = timezone.localdate()
        for drug in drugs.values():
            load_lot(drug, f"L{random.randint(10000, 99999)}", today + datetime.timedelta(days=random.choice([20, 200, 400])),
                     Decimal(random.choice([8, 40, 90])), coordinator, supplier="Farmacia territoriale")

        community = Community.default()
        temp = ParameterType.objects.get(code="temperatura")
        bp = ParameterType.objects.get(code="pressione")
        glyc = ParameterType.objects.get(code="glicemia")
        weight = ParameterType.objects.get(code="peso")
        now = timezone.now()
        start = now - datetime.timedelta(days=40)

        for first, last, sex, birth, cf, room, tag_names in GUESTS:
            if Guest.objects.filter(fiscal_code=cf).exists():
                continue
            guest = Guest.objects.create(
                community=community, first_name=first, last_name=last, sex=sex, birth_date=birth, fiscal_code=cf,
                room=room, admission_date=today - datetime.timedelta(days=400), residence_city="Milano",
                general_practitioner="Dott. Paolo Esposito", general_practitioner_phone="02 0000000",
                disability_description="Disabilità intellettiva (dati di fantasia per la demo)",
                diet="Mediterranea" if "Disfagia" not in tag_names else "Ipocalorica",
                diet_texture="frullata" if "Disfagia" in tag_names else "normale",
            )
            guest.created_at = start
            guest.save()
            guest.tags.set([tags[n] for n in tag_names])
            AdmissionEvent.objects.create(guest=guest, kind="admission", date=guest.admission_date)
            GuestContact.objects.create(guest=guest, kind="support_admin", name=f"Elena {last}", relationship="Sorella",
                                        phone="333 0000000", is_emergency_contact=True, can_receive_health_info=True,
                                        legal_reference="Decreto Tribunale (fittizio)")
            Diagnosis.objects.create(guest=guest, description="Disabilità intellettiva moderata", icd_code="F71", is_primary=True)

            if "Epilettico" in tag_names:
                Diagnosis.objects.create(guest=guest, description="Epilessia focale", icd_code="G40.1")
                Therapy.objects.create(guest=guest, drug=drugs["acido valproico"], dose=Decimal("1"), dose_unit="cp",
                                       schedule_times=["08:00", "20:00"], prescriber=users["doctor"],
                                       start_date=today - datetime.timedelta(days=90))
                Therapy.objects.create(guest=guest, drug=drugs["midazolam"], dose=Decimal("10"), dose_unit="mg",
                                       route="buccal", is_sos=True, sos_indication="Crisi epilettica > 3 minuti",
                                       sos_max_daily=2, sos_min_interval_hours=6, prescriber=users["doctor"])
                ClinicalEvent.objects.create(guest=guest, event_type="seizure", severity="medium", duration_minutes=2,
                                             occurred_at=now - datetime.timedelta(days=3, hours=2),
                                             description="Crisi tonico-clonica di circa 2 minuti, risolta spontaneamente.",
                                             actions_taken="Posizione laterale di sicurezza, monitoraggio.")
            if "Diabetico" in tag_names:
                Diagnosis.objects.create(guest=guest, description="Diabete mellito tipo 2", icd_code="E11")
                Therapy.objects.create(guest=guest, drug=drugs["metformina"], dose=Decimal("1"), dose_unit="cp",
                                       schedule_times=["08:00", "13:00", "20:00"], prescriber_name="Dott. Paolo Esposito",
                                       instructions="Durante i pasti")
            if first == "Sara":
                Allergy.objects.create(guest=guest, substance="paracetamolo", reaction="Orticaria", severity="moderate")
                Therapy.objects.create(guest=guest, drug=drugs["warfarin"], dose=Decimal("1"), dose_unit="cp",
                                       schedule_times=["18:00"], prescriber_name="Dott. Paolo Esposito")
            Therapy.objects.create(guest=guest, drug=drugs["paracetamolo"] if first != "Sara" else drugs["macrogol"],
                                   dose=Decimal("1"), dose_unit="cp" if first != "Sara" else "bustina", is_sos=True,
                                   sos_indication="TC > 38 °C o dolore" if first != "Sara" else "Stipsi",
                                   sos_max_daily=3, sos_requires_validation=False, prescriber_name="Dott. Paolo Esposito")

            for day in range(30, 0, -1):
                moment = now - datetime.timedelta(days=day, hours=random.randint(0, 3))
                ParameterReading.objects.create(guest=guest, parameter_type=temp, occurred_at=moment,
                                                value=Decimal(str(round(random.uniform(36.1, 37.3), 1))))
                if day % 3 == 0:
                    ParameterReading.objects.create(guest=guest, parameter_type=bp, occurred_at=moment,
                                                    value=Decimal(random.randint(110, 145)), value_2=Decimal(random.randint(65, 92)))
                if "Diabetico" in tag_names:
                    ParameterReading.objects.create(guest=guest, parameter_type=glyc, occurred_at=moment,
                                                    value=Decimal(random.randint(95, 210)))
                if day % 7 == 0:
                    ParameterReading.objects.create(guest=guest, parameter_type=weight, occurred_at=moment,
                                                    value=Decimal(str(round(random.uniform(60, 82), 1))))
                if day % 2 == 0 and not (first == "Luca" and day < 5):
                    EvacuationRecord.objects.create(guest=guest, occurred_at=moment, outcome=True, consistency="4")
            DiaryEntry.objects.create(guest=guest, occurred_at=now - datetime.timedelta(hours=20),
                                      text="Giornata serena, ha partecipato al laboratorio di pittura.")

            pai = PAI.objects.create(guest=guest, version=1, review_due=today + datetime.timedelta(days=120),
                                     summary="Mantenimento delle autonomie e benessere relazionale.",
                                     participants="Coordinatore, educatore, medico, amministratore di sostegno")
            for area, objective, intervention in [
                ("health", "Mantenere i parametri vitali nella norma", "Rilevazione parametri secondo programma"),
                ("autonomy", "Migliorare l'autonomia nell'igiene personale", "Affiancamento guidato al mattino"),
                ("behaviour", "Ridurre gli episodi di agitazione", "Routine strutturata e anticipazione dei cambiamenti"),
                ("social", "Partecipare ad attività di gruppo settimanali", "Laboratorio espressivo il martedì"),
            ]:
                PAIGoal.objects.create(pai=pai, area=area, objective=objective, intervention=intervention,
                                       responsible=users["operator"], verification_date=today + datetime.timedelta(days=60))
            pai.status = PAI.Status.ACTIVE
            pai.valid_from = today - datetime.timedelta(days=30)
            pai.approved_by = coordinator
            pai.approved_at = now - datetime.timedelta(days=30)
            pai.save()

            Appointment.objects.create(guest=guest, kind="specialist", title="Visita di controllo",
                                       scheduled_at=now + datetime.timedelta(days=random.randint(1, 10), hours=2),
                                       location="Ospedale – ambulatorio", doctor="Dott.ssa Gallo", companion=users["operator"])

        from fasas.protocols.engine import run_periodic_checks

        run_periodic_checks()
        self._billing(users)
        self._rota(users)
        self._novita(users)

    # --- Novità: attività a orario, cassa, scadenze del personale, indicatori, firma multipla, familiari ----------

    def _novita(self, users):
        from fasas.guests.models import Guest

        guests = {g.first_name: g for g in Guest.objects.exclude(status="archived")}
        if not guests:
            return
        with audit_context(user=users["coordinator"]):
            self._demo_care(users, guests)
            self._demo_cash(users, guests)
            self._demo_credentials(users)
            self._demo_quality(users, guests)
            self._demo_signing(users, guests)
            self._demo_families(users, guests)

    def _demo_care(self, users, guests):
        from fasas.care import services
        from fasas.care.models import CareTask

        if CareTask.objects.exists():
            return
        start = timezone.localdate() - datetime.timedelta(days=7)
        plans = [
            ("Giulia", {"kind": "repositioning", "every_hours": 2, "first_time": datetime.time(0),
                        "instructions": "Alternare fianco destro, sinistro e supino; controllare i talloni."}),
            ("Luca", {"kind": "hydration", "times": ["10:00", "16:00", "20:00"],
                      "instructions": "Almeno un bicchiere d'acqua; annotare se rifiuta."}),
            ("Mario", {"kind": "night_check", "times": ["23:00", "01:00", "03:00", "05:00"], "shifts": ["N"],
                       "instructions": "Controllo del respiro e della posizione (rischio crisi notturne)."}),
        ]
        now = timezone.now()
        for name, data in plans:
            if name not in guests:
                continue
            task = CareTask.objects.create(guest=guests[name], start_date=start, created_by=users["coordinator"], **data)
            # spunta delle attività già passate di oggi, tranne una lasciata «in ritardo» da mostrare
            slots = [s for s in services.shift_slots(*services.resolve_shift(now)) if s.task == task
                     and s.moment < now - datetime.timedelta(minutes=40)]
            for slot in slots[:-1]:
                try:
                    services.register_check(task, users["operator"], slot.day, slot.time, now=now,
                                            occurred_at=slot.moment + datetime.timedelta(minutes=5))
                except services.CareError:
                    pass

    def _demo_cash(self, users, guests):
        from fasas.personal.models import CashMovement, PersonalItem
        from fasas.personal.services import add_movement

        if CashMovement.objects.exists():
            return
        today = timezone.localdate()
        office = users["administrative"]
        for guest in guests.values():
            add_movement(guest, office, "deposit", "150.00", "Versamento mensile", today - datetime.timedelta(days=35),
                         counterpart=f"Elena {guest.last_name} (amministratrice di sostegno)")
            add_movement(guest, users["operator"], "expense", "18.00", "Parrucchiere", today - datetime.timedelta(days=20),
                         counterpart="Salone Bellezza (fittizio)")
            add_movement(guest, users["operator"], "expense", "6.50", "Merenda in gita", today - datetime.timedelta(days=9))
            add_movement(guest, office, "deposit", "100.00", "Versamento mensile", today - datetime.timedelta(days=4),
                         counterpart=f"Elena {guest.last_name} (amministratrice di sostegno)")
            add_movement(guest, users["operator"], "withdrawal", "10.00", "Contanti per il bar del centro diurno",
                         today - datetime.timedelta(days=2))
            PersonalItem.objects.create(guest=guest, name="Orologio da polso", description="Cinturino blu",
                                        received_on=guest.admission_date, received_from="Familiare",
                                        created_by=office)
            PersonalItem.objects.create(guest=guest, name="Radio portatile", value=Decimal("25.00"),
                                        received_on=today - datetime.timedelta(days=60), created_by=office)

    def _demo_credentials(self, users):
        from fasas.staffing.credentials import add_credential
        from fasas.staffing.models import CredentialType, StaffCredential

        if StaffCredential.objects.exists():
            return
        today = timezone.localdate()
        types = {t.name.split(" ")[0]: t for t in CredentialType.objects.all()}
        plan = [
            (users["operator"], "Sicurezza", today - datetime.timedelta(days=400), None),
            (users["operator"], "BLSD", today - datetime.timedelta(days=700), None),  # scade a breve
            (users["operator"], "Idoneità", today - datetime.timedelta(days=340), today + datetime.timedelta(days=25)),
            (users["coordinator"], "Sicurezza", today - datetime.timedelta(days=200), None),
            (users["coordinator"], "BLSD", today - datetime.timedelta(days=800), None),  # scaduto
            (users["coordinator"], "Preposto", today - datetime.timedelta(days=100), None),
            (users["coordinator"], "Antincendio", today - datetime.timedelta(days=500), None),
            (users["coordinator"], "Idoneità", today - datetime.timedelta(days=100), today + datetime.timedelta(days=265)),
        ]
        for user, key, obtained, expires in plan:
            if key in types:
                add_credential(user, types[key], obtained, users["coordinator"], expires_on=expires,
                               provider="Ente formatore di fantasia")

    def _demo_quality(self, users, guests):
        """Storico di un anno (cadute, una contenzione, un ricovero, una lesione) per vedere gli indicatori."""
        from fasas.clinical.models import ClinicalEvent, Restraint
        from fasas.guests.models import AdmissionEvent
        from fasas.wounds.models import Wound

        if ClinicalEvent.objects.filter(event_type="fall").exists():
            return
        now = timezone.now()
        rng = random.Random(7)
        names = list(guests)
        for months_ago in range(11, -1, -1):
            for _ in range(rng.choice([0, 1, 1, 2, 3])):
                moment = now - datetime.timedelta(days=30 * months_ago + rng.randint(0, 25), hours=rng.randint(0, 12))
                if moment > now:
                    continue
                serious = rng.random() < 0.2
                ClinicalEvent.objects.create(
                    guest=guests[rng.choice(names)], event_type="fall", occurred_at=moment,
                    severity="high" if serious else "low", description="Caduta (dato di fantasia per la demo).",
                    injuries="Ematoma all'anca" if serious else "")
        if "Mario" in guests:
            Restraint.objects.create(guest=guests["Mario"], restraint_type="bed_rails", occurred_at=now - datetime.timedelta(days=150),
                                     ended_at=now - datetime.timedelta(days=120), reason="Rischio di caduta notturna dopo crisi",
                                     alternatives_tried="Letto basso, sensore di presenza", authorized_by=users["doctor"],
                                     authorization_date=timezone.localdate() - datetime.timedelta(days=150),
                                     responsible_operator=users["operator"])
        if "Luca" in guests:
            day = timezone.localdate() - datetime.timedelta(days=95)
            AdmissionEvent.objects.create(guest=guests["Luca"], kind="hospitalization", date=day,
                                          notes="Ricovero per iperglicemia (dato di fantasia)")
            AdmissionEvent.objects.create(guest=guests["Luca"], kind="return", date=day + datetime.timedelta(days=4))
        if "Giulia" in guests:
            Wound.objects.create(guest=guests["Giulia"], kind="pressure", site="heel", side="left", origin="in_house",
                                 stage="1", occurred_at=now - datetime.timedelta(days=50))

    def _demo_signing(self, users, guests):
        """Documenti da firmare e un certificato DI PROVA per il medico (firma non qualificata, solo per provare)."""
        from fasas.documents.models import Document
        from fasas.documents.services import create_document
        from fasas.reports.pdf import Document as PdfDocument
        from fasas.signatures.models import SigningCredential
        from fasas.signatures.services import register_pkcs12

        if Document.objects.filter(title__startswith="Relazione periodica").exists():
            return
        for guest in list(guests.values())[:3]:
            pdf = PdfDocument(f"Relazione periodica – {guest.first_name} {guest.last_name}", "Documento di fantasia per la demo")
            pdf.text("Contenuto di esempio: nessun dato sanitario reale.")
            create_document(guest, Document.Category.MEDICAL_REPORT, f"Relazione periodica {guest.first_name}",
                            user=users["coordinator"], data=pdf.build(), filename="relazione.pdf")
        if not SigningCredential.objects.filter(user=users["doctor"]).exists():
            register_pkcs12(users["doctor"], _test_certificate(demo_password()), demo_password())

    def _demo_families(self, users, guests):
        from fasas.core.models import SystemConfig
        from fasas.documents.models import Document
        from fasas.documents.services import create_document
        from fasas.families import services
        from fasas.families.models import FamilyLink
        from fasas.reports.pdf import Document as PdfDocument

        family = users.get("family")
        if family is None or "Mario" not in guests or FamilyLink.objects.exists():
            return
        # Nella demo l'area familiari è accesa per mostrarla; in struttura resta spenta fino al parere del DPO
        config = SystemConfig.get()
        config.disabled_modules = [k for k in (config.disabled_modules or []) if k != "families"]
        config.save(update_fields=["disabled_modules"])
        mario = guests["Mario"]
        link = FamilyLink.objects.create(user=family, guest=mario, relation="support", description="sorella",
                                         basis="Decreto di nomina dell'amministratore di sostegno (fittizio)",
                                         can_see_documents=True, can_see_cash=True, created_by=users["coordinator"])
        services.send_message(link, family, "Buongiorno, domenica vorrei portare Mario a pranzo fuori. È possibile?", True)
        services.send_message(link, users["coordinator"], "Buongiorno Elena, certo: lo prepariamo per le 12. "
                              "Ricordi la terapia delle 13 che le consegniamo in busta.", False)
        services.send_message(link, family, "Perfetto, grazie!", True)
        sunday = timezone.localdate() + datetime.timedelta(days=(6 - timezone.localdate().weekday()) or 7)
        services.request_visit(link, family, sunday, datetime.time(12), 2, "Pranzo fuori con Mario")
        services.request_visit(link, family, sunday + datetime.timedelta(days=7), datetime.time(16), 1)
        pdf = PdfDocument("Programma delle attività del mese", "Documento di fantasia per la demo")
        pdf.text("Laboratorio di pittura il martedì, uscita al mercato il giovedì, musica il venerdì.")
        document = create_document(mario, Document.Category.OTHER, "Programma delle attività del mese",
                                   user=users["coordinator"], data=pdf.build(), filename="attivita.pdf")
        services.share_document(document, users["coordinator"], "Il programma di questo mese")


def _test_certificate(passphrase):
    """Certificato autofirmato DI PROVA per il medico della demo: la firma non è qualificata e lo dice."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Marta Medico (CERTIFICATO DI PROVA, non valido)")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"prova", key, cert, None,
                                                 serialization.BestAvailableEncryption(passphrase.encode()))
