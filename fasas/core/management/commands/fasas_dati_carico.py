"""Dati di fantasia per le prove di carico (solo installazioni di prova): ospiti, terapie, storico, operatori."""
import datetime
import random
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

FIRST = ["Mario", "Lucia", "Paolo", "Anna", "Marco", "Giulia", "Luca", "Sara", "Andrea", "Elena"]
LAST = ["Rossi", "Bianchi", "Verdi", "Neri", "Gallo", "Costa", "Fontana", "Conti", "Greco", "Romano"]


class Command(BaseCommand):
    help = "Crea ospiti, terapie, 30 giorni di storico e operatori «caricoNN» per la prova di carico (solo DEBUG)"

    def add_arguments(self, parser):
        parser.add_argument("--ospiti", type=int, default=60)
        parser.add_argument("--operatori", type=int, default=20)
        parser.add_argument("--giorni", type=int, default=30)
        parser.add_argument("--password", default="Carico-Prova-2026!")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Solo nelle installazioni di prova (DJANGO_DEBUG=1): crea dati di fantasia.")
        from fasas.accounts.models import Role, User
        from fasas.audit.context import audit_context
        from fasas.clinical.models import ParameterReading, ParameterType, Therapy, TherapyAdministration
        from fasas.core.models import Community
        from fasas.core.shifts import resolve_shift
        from fasas.daily.models import DiaryEntry
        from fasas.guests.models import Guest
        from fasas.pharmacy.models import Drug

        random.seed(2026)
        operators = []
        for i in range(1, options["operatori"] + 1):
            user, _ = User.objects.get_or_create(username=f"carico{i:02d}", defaults={
                "role": Role.OPERATOR, "first_name": "Operatore", "last_name": f"Carico {i:02d}"})
            user.set_password(options["password"])
            user.save()
            operators.append(user)
        drugs = [Drug.objects.get_or_create(name=f"Farmaco prova {n}", defaults={
            "active_ingredient": f"principio {n}", "atc_code": f"N0{n % 9}AA0{n % 9}"})[0] for n in range(1, 16)]
        temperature = ParameterType.objects.filter(active=True).first()
        now = timezone.now()
        start = now - datetime.timedelta(days=options["giorni"])
        guests = []
        with audit_context(user=operators[0]):
            for n in range(options["ospiti"]):
                guest = Guest.objects.create(
                    community=Community.default(), fiscal_code=f"PRVCRC{n:02d}A01H501{chr(65 + n % 26)}"[:16],
                    first_name=random.choice(FIRST), last_name=f"{random.choice(LAST)} {n:02d}",
                    birth_date=datetime.date(1960 + n % 30, 1 + n % 12, 1 + n % 28),
                    admission_date=start.date() - datetime.timedelta(days=30))
                guests.append(guest)
                for k in range(3):
                    Therapy.objects.create(guest=guest, drug=drugs[(n + k) % len(drugs)], dose=Decimal("1"),
                                           schedule_times=["08:00", "13:00", "20:00"], prescriber_name="Dott. Prova",
                                           start_date=start.date())
        administrations, readings, diary = [], [], []
        for guest in guests:
            therapies = list(guest.therapies.all())
            for day in range(options["giorni"]):
                date = (start + datetime.timedelta(days=day)).date()
                for therapy in therapies:
                    for hhmm in therapy.schedule_times:
                        moment = timezone.make_aware(datetime.datetime.combine(date, datetime.time.fromisoformat(hhmm)))
                        shift_date, shift = resolve_shift(moment)
                        administrations.append(TherapyAdministration(
                            guest=guest, therapy=therapy, occurred_at=moment, shift_date=shift_date, shift=shift,
                            scheduled_date=date, scheduled_time=datetime.time.fromisoformat(hhmm),
                            created_by=random.choice(operators)))
                for hour in (8, 20):
                    moment = timezone.make_aware(datetime.datetime.combine(date, datetime.time(hour)))
                    shift_date, shift = resolve_shift(moment)
                    if temperature:
                        readings.append(ParameterReading(
                            guest=guest, parameter_type=temperature, occurred_at=moment, shift_date=shift_date,
                            shift=shift, value=Decimal("36.5"), created_by=random.choice(operators)))
                    diary.append(DiaryEntry(guest=guest, occurred_at=moment, shift_date=shift_date, shift=shift,
                                            text="Giornata regolare (testo di fantasia).",
                                            created_by=random.choice(operators)))
        TherapyAdministration.objects.bulk_create(administrations, batch_size=2000)
        ParameterReading.objects.bulk_create(readings, batch_size=2000)
        DiaryEntry.objects.bulk_create(diary, batch_size=2000)
        self.stdout.write(self.style.SUCCESS(
            f"{len(guests)} ospiti, {len(administrations)} somministrazioni, {len(readings)} parametri, "
            f"{len(diary)} voci di diario, operatori carico01–carico{len(operators):02d}."))
