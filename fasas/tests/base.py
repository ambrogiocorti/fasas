import datetime
import io
import shutil
import tempfile
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from fasas.accounts.models import Role, User
from fasas.audit.context import audit_context
from fasas.core.models import Community
from fasas.guests.models import Guest

PASSWORD = "Test-Password-2026!"
_MEDIA = tempfile.mkdtemp(prefix="fasas-test-media-")
_BACKUP = tempfile.mkdtemp(prefix="fasas-test-backup-")


@override_settings(MEDIA_ROOT=_MEDIA, FASAS_BACKUP_DIR=__import__("pathlib").Path(_BACKUP),
                   FASAS_ALLOWED_NETWORKS=[], PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FasasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("fasas_setup", stdout=io.StringIO())
        cls.admin = cls.make_user("admin", Role.ADMIN)
        cls.coordinator = cls.make_user("coord", Role.COORDINATOR)
        cls.operator = cls.make_user("oper", Role.OPERATOR)
        cls.doctor = cls.make_user("doc", Role.DOCTOR)
        cls.guest = cls.make_guest()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    @staticmethod
    def make_user(username, role):
        user = User(username=username, role=role, first_name=username.capitalize(), last_name="Test")
        user.set_password(PASSWORD)
        user.save()
        return user

    @staticmethod
    def make_guest(fiscal_code="RSSMRA80A01F205X", **extra):
        data = {"first_name": "Mario", "last_name": "Rossi", "birth_date": datetime.date(1980, 1, 1),
                "admission_date": timezone.localdate() - datetime.timedelta(days=10)}
        data.update(extra)
        guest = Guest.objects.create(community=Community.default(), fiscal_code=fiscal_code, **data)
        # Mezzogiorno del giorno d'ingresso: «adesso meno 10 giorni» può cadere in un altro giorno locale
        # quando nel frattempo è cambiata l'ora legale
        guest.created_at = timezone.make_aware(datetime.datetime.combine(data["admission_date"], datetime.time(12)))
        guest.save()
        return guest

    @staticmethod
    def make_drug(name="Tachipirina", ingredient="paracetamolo", atc="N02BE01", min_stock=0):
        from fasas.pharmacy.models import Drug

        return Drug.objects.create(name=name, active_ingredient=ingredient, atc_code=atc, min_stock=Decimal(min_stock))

    def make_therapy(self, drug=None, **extra):
        from fasas.clinical.models import Therapy

        data = {"guest": self.guest, "drug": drug or self.make_drug(), "dose": Decimal("1"), "dose_unit": "cp",
                "schedule_times": ["08:00", "20:00"], "prescriber_name": "Dott. Test",
                "start_date": timezone.localdate() - datetime.timedelta(days=5)}
        data.update(extra)
        with audit_context(user=self.coordinator):
            return Therapy.objects.create(**data)

    def login(self, user):
        self.client.force_login(user)
