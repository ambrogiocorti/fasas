"""Versione cloud: pianificatore senza Redis, controlli d'avvio, primo amministratore, file su object storage, SQL."""
import datetime
import io
import os
import re
import tarfile
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.checks import Error, Warning
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from fasas.accounts.models import Role, User
from fasas.backups import services
from fasas.core import scheduler
from fasas.core.cloud import cloud_checks
from fasas.core.encryption import read_encrypted, store_encrypted
from fasas.core.models import JobRun

from .base import FasasTestCase

ROME = ZoneInfo("Europe/Rome")
UTC = datetime.timezone.utc
IN_MEMORY = {"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


def rome(*args):
    return datetime.datetime(*args, tzinfo=ROME)


class OrariTest(SimpleTestCase):
    def test_campi_come_cron(self):
        self.assertEqual(scheduler.parse_field("*/15", 0, 59), {0, 15, 30, 45})
        self.assertEqual(scheduler.parse_field("6,18", 0, 23), {6, 18})
        self.assertEqual(scheduler.parse_field("1-5", 0, 6), {1, 2, 3, 4, 5})
        self.assertEqual(scheduler.parse_field("10-20/5", 0, 59), {10, 15, 20})
        for wrong in ("60", "*/0", "5-2", "x"):
            with self.assertRaises(ValueError):
                scheduler.parse_field(wrong, 0, 59)
        with self.assertRaises(ValueError):
            scheduler.compile_spec({"minuto": "5"})

    def test_stessi_orari_di_celery_beat(self):
        from celery.schedules import crontab

        from config.celery import app

        beat = app.conf.beat_schedule
        self.assertEqual(set(beat), {name for name, _, _ in scheduler.SCHEDULE})
        for name, job, spec in scheduler.SCHEDULE:
            self.assertEqual(beat[name]["args"], (job,))
            self.assertEqual(beat[name]["schedule"], crontab(**spec))
        from fasas.core.jobs import JOBS

        self.assertTrue({job for _, job, _ in scheduler.SCHEDULE} <= set(JOBS))

    def test_job_dovuti_in_un_intervallo(self):
        due = scheduler.due(rome(2026, 11, 6, 2, 29), rome(2026, 11, 6, 2, 31))
        self.assertEqual(due["backup"], rome(2026, 11, 6, 2, 30).astimezone(UTC))
        self.assertIn("close_shifts", due)
        self.assertNotIn("audit_verify", due)  # alle 02:00, fuori dall'intervallo
        # un job dovuto più volte nell'intervallo parte una volta sola, all'orario più recente
        due = scheduler.due(rome(2026, 11, 6, 9, 0), rome(2026, 11, 6, 10, 0))
        self.assertEqual(due["close_shifts"], rome(2026, 11, 6, 10, 0).astimezone(UTC))

    def test_trimestrale(self):
        self.assertIn("restore_test", scheduler.due(rome(2026, 10, 1, 4, 14), rome(2026, 10, 1, 4, 15)))
        self.assertNotIn("restore_test", scheduler.due(rome(2026, 11, 1, 4, 14), rome(2026, 11, 1, 4, 15)))

    def test_ora_legale_in_avanti_non_perde_il_backup(self):
        # 28/03/2027: alle 02:00 gli orologi passano alle 03:00, le 02:30 non esistono
        due = scheduler.due(rome(2027, 3, 28, 1, 55), rome(2027, 3, 28, 3, 1))
        self.assertIn("backup", due)
        self.assertIn("audit_verify", due)

    def test_ora_legale_indietro_non_ripete_il_backup(self):
        # 25/10/2026: alle 03:00 gli orologi tornano alle 02:00; l'ora ripetuta va dalle 01:00 alle 02:00 UTC
        due = scheduler.due(datetime.datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
                            datetime.datetime(2026, 10, 25, 1, 59, tzinfo=UTC))
        self.assertNotIn("backup", due)
        self.assertNotIn("audit_verify", due)
        self.assertIn("close_shifts", due)  # i job frequenti continuano


class PianificatoreTest(TestCase):
    def setUp(self):
        # nei test la connessione è dentro una transazione: non va chiusa tra un job e l'altro
        self.enterContext(mock.patch("fasas.core.scheduler.close_old_connections"))

    def test_prenotazione_una_sola_volta_per_orario(self):
        slot = timezone.now().replace(second=0, microsecond=0)
        self.assertTrue(scheduler.claim("backup", slot))
        self.assertFalse(scheduler.claim("backup", slot))  # un'altra copia del servizio arriva tardi
        self.assertTrue(scheduler.claim("backup", slot + datetime.timedelta(days=1)))

    def test_recupero_dei_job_saltati_e_errori(self):
        done = []

        def runner(job):
            done.append(job)
            if job == "stock":
                raise RuntimeError("guasto di prova")

        now = rome(2026, 11, 6, 8, 0)
        result = scheduler.run_due(now - scheduler.CATCH_UP, now, runner)
        for job in ("backup", "audit_verify", "stock", "pai_reviews", "close_shifts"):
            self.assertIn(job, done)
        self.assertEqual(done.count("backup"), 1)
        self.assertIn("documents", result)  # un job fallito non ferma gli altri
        # al riavvio subito dopo nulla riparte: ogni orario è già prenotato
        done.clear()
        scheduler.run_due(now - scheduler.CATCH_UP, now, runner)
        self.assertEqual(done, [])

    def test_ciclo_con_orologio_finto(self):
        times = [rome(2026, 11, 6, 2, 29, 59), rome(2026, 11, 6, 2, 30, 1), rome(2026, 11, 6, 2, 30, 2)]
        clock = mock.Mock(side_effect=lambda: times[0])
        done = []
        loop = scheduler.Scheduler(runner=done.append, sleep=lambda seconds: None, clock=clock)
        last = loop.tick(rome(2026, 11, 6, 2, 28))
        self.assertNotIn("backup", done)
        times.pop(0)
        loop.tick(last)
        self.assertIn("backup", done)
        # un salto dell'orologio troppo grande non fa ripartire una giornata di job
        done.clear()
        times[0] = rome(2026, 11, 9, 12, 0, 30)
        loop.tick(rome(2026, 11, 6, 2, 31))
        self.assertNotIn("backup", done)

    def test_comando_una_volta(self):
        with mock.patch("fasas.core.jobs.run_job") as run_job:
            call_command("fasas_pianificatore", "--una-volta", stdout=io.StringIO())
        self.assertTrue(run_job.called)
        self.assertTrue(JobRun.objects.filter(name="close_shifts", last_started__isnull=False).exists())
        out = io.StringIO()
        call_command("fasas_pianificatore", "--orari", stdout=out)
        self.assertIn("backup", out.getvalue())


class ControlliCloudTest(SimpleTestCase):
    def ids(self, **overrides):
        import warnings

        values = {"FASAS_CLOUD": True, "DEBUG": False, "FASAS_PUBLIC_HOSTS": ["fasas.esempio.it"],
                  "FASAS_S3_BUCKET": "", "FASAS_PERSISTENT_DISK": False,
                  "DATABASES": {"default": {**settings.DATABASES["default"],
                                            "ENGINE": "django.db.backends.postgresql", "PORT": "5432"}}}
        values.update(overrides)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # «Overriding setting DATABASES»: qui si leggono solo i valori
            with override_settings(**values):
                return {item.id: type(item) for item in cloud_checks()}

    def test_spenta_nessun_controllo(self):
        with override_settings(FASAS_CLOUD=False):
            self.assertEqual(cloud_checks(), [])

    def test_senza_storage_dei_file_si_ferma(self):
        found = self.ids()
        self.assertIs(found["fasas.E102"], Error)
        self.assertIs(found["fasas.W102"], Warning)  # nessuna copia fuori sede dei backup
        self.assertNotIn("fasas.E102", self.ids(FASAS_PERSISTENT_DISK=True))

    def test_storage_completo(self):
        storages = {"default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {
            "endpoint_url": "https://abc.storage.supabase.co/storage/v1/s3", "access_key": "id", "secret_key": "segreto"}},
            "staticfiles": settings.STORAGES["staticfiles"]}
        found = self.ids(FASAS_S3_BUCKET="fasas-documenti", STORAGES=storages)
        self.assertNotIn("fasas.E102", found)
        self.assertNotIn("fasas.E103", found)
        storages["default"]["OPTIONS"]["secret_key"] = None
        self.assertIn("fasas.E103", self.ids(FASAS_S3_BUCKET="fasas-documenti", STORAGES=storages))

    def test_dominio_debug_database(self):
        found = self.ids(FASAS_PUBLIC_HOSTS=[], DEBUG=True,
                         DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
        self.assertIn("fasas.E104", found)
        self.assertIn("fasas.E105", found)
        self.assertIn("fasas.E101", found)
        found = self.ids(DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "PORT": "6543"}})
        self.assertIs(found["fasas.W101"], Warning)  # pooler in modalità transazione: pg_dump non va

    def test_domini_dalle_variabili(self):
        from config.settings import public_hosts

        env = {"FASAS_DOMAIN": "https://FASAS.Esempio.it/, fasas2.esempio.it", "RENDER_EXTERNAL_HOSTNAME": "fasas.onrender.com"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(public_hosts(), ["fasas.esempio.it", "fasas2.esempio.it", "fasas.onrender.com"])


@override_settings(ALLOWED_HOSTS=["fasas.esempio.it"], FASAS_ALLOWED_NETWORKS=["192.168.1.0/24"])
class SaluteDaHostInternoTest(TestCase):
    def test_salute_risponde_con_qualsiasi_host_e_rete(self):
        response = self.client.get("/salute/", HTTP_HOST="10.0.4.7:10000", REMOTE_ADDR="10.0.4.1")
        self.assertIn(response.status_code, (200, 503))
        self.assertIn("status", response.json())
        self.assertNotIn("checks", response.json())
        # tutto il resto continua a controllare rete e Host
        self.assertEqual(self.client.get("/accesso/entra/", HTTP_HOST="fasas.esempio.it", REMOTE_ADDR="10.0.4.1")
                         .status_code, 403)
        self.assertEqual(self.client.get("/accesso/entra/", HTTP_HOST="10.0.4.7:10000", REMOTE_ADDR="192.168.1.20")
                         .status_code, 400)


class PrimoAmministratoreTest(TestCase):
    ENV = {"FASAS_ADMIN_USERNAME": "direzione", "FASAS_ADMIN_PASSWORD": "Una-Password-Lunga-2026!"}

    def test_crea_una_volta_sola(self):
        with mock.patch.dict(os.environ, self.ENV):
            call_command("fasas_primo_amministratore", stdout=io.StringIO())
            user = User.objects.get(username="direzione")
            self.assertTrue(user.is_superuser)
            self.assertEqual(user.role, Role.ADMIN)
            self.assertTrue(user.check_password(self.ENV["FASAS_ADMIN_PASSWORD"]))
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"FASAS_ADMIN_PASSWORD": "Altra-Password-2026!"}):
                call_command("fasas_primo_amministratore", stdout=out)
            self.assertIn("togliere FASAS_ADMIN_PASSWORD", out.getvalue())
        user.refresh_from_db()
        self.assertTrue(user.check_password(self.ENV["FASAS_ADMIN_PASSWORD"]))  # la password non viene cambiata
        self.assertEqual(User.objects.count(), 1)

    def test_password_debole_rifiutata(self):
        with mock.patch.dict(os.environ, {**self.ENV, "FASAS_ADMIN_PASSWORD": "12345678"}):
            with self.assertRaises(CommandError):
                call_command("fasas_primo_amministratore", stdout=io.StringIO())
        self.assertFalse(User.objects.exists())

    def test_senza_variabili_non_fa_nulla(self):
        with mock.patch.dict(os.environ, {"FASAS_ADMIN_USERNAME": "", "FASAS_ADMIN_PASSWORD": ""}):
            out = io.StringIO()
            call_command("fasas_primo_amministratore", stdout=out)
        self.assertIn("Nessun gestore del sistema", out.getvalue())
        self.assertFalse(User.objects.exists())


@override_settings(STORAGES=IN_MEMORY)
class BackupConFileSuStorageTest(FasasTestCase):
    def test_backup_e_ripristino_dei_file_dallo_storage(self):
        self.assertFalse(services.media_on_disk())
        names = [store_encrypted(b"referto di prova", "documents/1"), store_encrypted(b"seconda prova", "documents/2")]
        record = services.create_backup()
        self.assertEqual(record.status, "ok", record.error)
        self.assertTrue(services.verify_backup(record))
        workdir = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        services._decrypt_file(record.path, workdir / "b.tar.gz", record.sha256)
        with tarfile.open(workdir / "b.tar.gz") as archive:
            archive.extractall(workdir, filter="data")
        with tarfile.open(workdir / "media.tar") as media:
            self.assertEqual(sorted(media.getnames()), sorted(f"media/{name}" for name in names))
            media.extractall(workdir / "r", filter="data")
        for name in names:
            default_storage.delete(name)
        services._restore_media(workdir / "r" / "media")
        services._restore_media(workdir / "r" / "media")  # una seconda volta: stessi nomi, nessun doppione
        self.assertEqual(sorted(services.storage_files(default_storage)), sorted(names))
        self.assertEqual(read_encrypted(names[0]), b"referto di prova")

    def test_salute_controlla_lo_storage(self):
        from fasas.core import monitoring

        monitoring._storage_state["value"] = None
        checks = {name: (state, detail) for name, state, detail in monitoring.checks()}
        self.assertEqual(checks["file"], ("ok", "object storage raggiungibile"))
        monitoring._storage_state["value"] = None
        with mock.patch("django.core.files.storage.InMemoryStorage.exists", side_effect=OSError("rete")):
            checks = {name: (state, detail) for name, state, detail in monitoring.checks()}
        self.assertEqual(checks["file"][0], "error")
        self.assertNotIn("rete", checks["file"][1])
        monitoring._storage_state["value"] = None


class PgDumpTest(SimpleTestCase):
    def test_solo_gli_schemi_indicati(self):
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            return mock.Mock(returncode=0, stderr="")

        with override_settings(FASAS_BACKUP_PG_SCHEMAS=["public"]), \
                mock.patch.object(services.connection, "vendor", "postgresql"), \
                mock.patch("fasas.backups.services.shutil.which", return_value="/usr/bin/pg_dump"), \
                mock.patch("fasas.backups.services.subprocess.run", side_effect=fake_run):
            services._dump_database(Path("/tmp"))
        self.assertIn("--schema=public", captured["args"])

    def test_indice_senza_lo_schema_public(self):
        listing = ("3; 2615 2200 SCHEMA - public pg_database_owner\n"
                   "4012; 0 0 COMMENT - SCHEMA public pg_database_owner\n"
                   "215; 1259 16390 TABLE public guests_guest postgres\n")
        with mock.patch("fasas.backups.services.subprocess.run",
                        return_value=mock.Mock(returncode=0, stdout=listing, stderr="")):
            workdir = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
            lines = services._restore_list(workdir / "database.dump", workdir).read_text().splitlines()
        self.assertEqual(lines, [";3; 2615 2200 SCHEMA - public pg_database_owner",
                                 ";4012; 0 0 COMMENT - SCHEMA public pg_database_owner",
                                 "215; 1259 16390 TABLE public guests_guest postgres"])


class MigrazioniSupabaseTest(SimpleTestCase):
    FOLDER = Path(settings.BASE_DIR) / "supabase" / "migrations"

    def test_sql_allineato_alle_migrazioni_di_django(self):
        """Se fallisce: rigenerare con «python scripts/genera_migrazioni_supabase.py <database vuoto>»."""
        schema = next(self.FOLDER.glob("*_fasas_schema_e_dati_iniziali.sql")).read_text(encoding="utf-8")
        rows = set()
        for insert in re.finditer(r"INSERT INTO public\.django_migrations .*?;\n", schema, re.S):
            rows.update(re.findall(r"\(\d+, '(\w+)', '(\w+)', '[^']+'\)", insert.group(0)))
        loader = MigrationLoader(None, ignore_no_migrations=True)
        self.assertEqual(rows, set(loader.disk_migrations))

    def test_sql_eseguibile_dall_editor_di_supabase(self):
        for path in self.FOLDER.glob("*.sql"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\\", f"{path.name}: comandi di psql non accettati dall'editor SQL")
            self.assertNotIn("OWNER TO", text, path.name)
            self.assertNotIn("GRANT ", text.replace("REVOKE", ""), path.name)
            self.assertNotIn("transaction_timeout", text, path.name)  # PostgreSQL 15 non lo conosce
            self.assertNotIn("audit_auditlog VALUES", text, path.name)
        security = next(self.FOLDER.glob("*_fasas_protezione_api.sql")).read_text(encoding="utf-8")
        for role in ("anon", "authenticated", "service_role"):
            self.assertIn(f"'{role}'", security)
        self.assertIn("ENABLE ROW LEVEL SECURITY", security)


class ProtezioneApiTest(TestCase):
    def test_ruoli_delle_api(self):
        from fasas.core.supabase import API_ROLES, harden

        self.assertEqual(API_ROLES, ("anon", "authenticated", "service_role"))
        if connection.vendor != "postgresql":
            self.assertEqual(harden(connection), {"skipped": "non PostgreSQL"})


class DatabaseDedicatoTest(TestCase):
    """Il FASAS non si installa in un database con tabelle di altre applicazioni e non le tocca mai."""

    def test_controllo_prima_di_migrate(self):
        from fasas.core.cloud import dedicated_database_check

        with override_settings(FASAS_CLOUD=True), \
                mock.patch("fasas.core.supabase.foreign_tables", return_value=["bars", "orders"]):
            errors = dedicated_database_check(databases=["default"])
            self.assertEqual([e.id for e in errors], ["fasas.E107"])
            self.assertIn("bars, orders", errors[0].msg)
            self.assertEqual(dedicated_database_check(databases=None), [])  # «check» senza database: nessuna query
        with override_settings(FASAS_CLOUD=False), \
                mock.patch("fasas.core.supabase.foreign_tables", return_value=["orders"]):
            if "supabase." not in str(settings.DATABASES["default"].get("HOST") or ""):
                self.assertEqual(dedicated_database_check(databases=["default"]), [])  # installazione in struttura

    def test_database_del_fasas_senza_tabelle_estranee(self):
        from fasas.core.supabase import fasas_tables, foreign_tables

        self.assertEqual(foreign_tables(connection), [])
        self.assertIn("django_migrations", fasas_tables(connection))
        self.assertIn("guests_guest", fasas_tables(connection))

    def test_protezione_non_tocca_tabelle_di_altre_applicazioni(self):
        if connection.vendor != "postgresql":
            self.skipTest("solo PostgreSQL")
        from fasas.core.supabase import foreign_tables, harden

        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE public.altra_app_ordini (id serial PRIMARY KEY)")
        try:
            self.assertEqual(foreign_tables(connection), ["altra_app_ordini"])
            result = harden(connection)
            self.assertEqual(result["foreign_tables"], 1)
            with connection.cursor() as cursor:
                cursor.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'altra_app_ordini'")
                self.assertFalse(cursor.fetchone()[0])
                cursor.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'guests_guest'")
                self.assertTrue(cursor.fetchone()[0])
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE public.altra_app_ordini")

    def test_sql_solo_su_progetto_dedicato(self):
        folder = Path(settings.BASE_DIR) / "supabase" / "migrations"
        schema = next(folder.glob("*_fasas_schema_e_dati_iniziali.sql")).read_text(encoding="utf-8")
        guard = schema.index("RAISE EXCEPTION")
        self.assertLess(guard, schema.index("CREATE TABLE"))  # il controllo viene prima di creare qualsiasi cosa
        security = next(folder.glob("*_fasas_protezione_api.sql")).read_text(encoding="utf-8")
        self.assertNotIn("ALL TABLES IN SCHEMA", security)
        self.assertIn("'guests_guest'", security)
        tables = set(re.findall(r"^        '(\w+)',?$", security, re.M))
        self.assertEqual(tables, set(re.findall(r"^CREATE TABLE public\.(\w+) \(", schema, re.M)))


class DominioDellaStrutturaTest(SimpleTestCase):
    def middleware(self):
        from django.http import HttpResponse

        from fasas.core.middleware import CanonicalDomainMiddleware

        return CanonicalDomainMiddleware(lambda request: HttpResponse("OK"))

    @override_settings(FASAS_CANONICAL_REDIRECT=True, FASAS_CANONICAL_HOST="fasas.online",
                       ALLOWED_HOSTS=["fasas.online", "www.fasas.online", "fasas-online.onrender.com"])
    def test_un_solo_indirizzo(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        middleware = self.middleware()
        self.assertEqual(middleware(factory.get("/accesso/entra/", HTTP_HOST="fasas.online")).status_code, 200)
        www = middleware(factory.get("/ospiti/?q=1", HTTP_HOST="www.fasas.online"))
        self.assertEqual((www.status_code, www["Location"]), (301, "https://fasas.online/ospiti/?q=1"))
        technical = middleware(factory.get("/", HTTP_HOST="fasas-online.onrender.com"))
        self.assertEqual(technical["Location"], "https://fasas.online/")
        api = middleware(factory.post("/api/firma/v1/abbina/", HTTP_HOST="fasas-online.onrender.com"))
        self.assertEqual(api.status_code, 404)

    @override_settings(FASAS_CANONICAL_REDIRECT=False, FASAS_CANONICAL_HOST="fasas.online", ALLOWED_HOSTS=["127.0.0.1"])
    def test_versione_locale_non_cambia(self):
        from django.test import RequestFactory

        self.assertEqual(self.middleware()(RequestFactory().get("/", HTTP_HOST="127.0.0.1")).status_code, 200)

    def test_dominio_dalle_variabili(self):
        from config.settings import _hosts

        with mock.patch.dict(os.environ, {"FASAS_DOMAIN": "https://Fasas.online/, www.fasas.online"}):
            self.assertEqual(_hosts("FASAS_DOMAIN"), ["fasas.online", "www.fasas.online"])


@override_settings(FASAS_PRESENTAZIONE=True)
class PresentazioneTest(TestCase):
    """Versione di presentazione online: dati inventati, niente configurazione, mai confusa con una vera."""

    def test_pagina_di_accesso_con_avviso_utenti_e_password(self):
        from fasas.core.management.commands.fasas_demo import DEMO_PASSWORD

        page = self.client.get("/accesso/entra/").content.decode()
        self.assertIn("Versione di presentazione", page)
        self.assertIn("coordinatore", page)
        self.assertIn(DEMO_PASSWORD, page)
        with mock.patch.dict(os.environ, {"FASAS_PRESENTAZIONE_PASSWORD": "Una-Password-Riservata-1"}):
            page = self.client.get("/accesso/entra/").content.decode()
        self.assertIn("Versione di presentazione", page)
        self.assertNotIn("Una-Password-Riservata-1", page)
        self.assertNotIn(DEMO_PASSWORD, page)

    def test_password_riservata_per_gli_utenti_di_prova(self):
        with mock.patch.dict(os.environ, {"FASAS_PRESENTAZIONE_PASSWORD": "Una-Password-Riservata-1"}):
            call_command("fasas_demo", "--ambiente-di-prova", stdout=io.StringIO())
        admin = User.objects.get(username="gestore")
        self.assertTrue(admin.check_password("Una-Password-Riservata-1"))

    def test_niente_backup_ne_apparecchi_della_struttura(self):
        due = scheduler.due(rome(2026, 11, 6, 2, 29), rome(2026, 11, 6, 2, 31))
        self.assertNotIn("backup", due)
        self.assertNotIn("ups", due)
        self.assertNotIn("continuity", due)
        self.assertIn("close_shifts", due)
        self.assertEqual(cloud_checks(), [])
        from fasas.core import monitoring

        checks = {name: state for name, state, _ in monitoring.checks()}
        self.assertEqual(checks["backup"], "ok")

    @override_settings(FASAS_PRESENTAZIONE=False)
    def test_installazione_normale_senza_avviso(self):
        self.assertNotIn("Versione di presentazione", self.client.get("/accesso/entra/").content.decode())
        self.assertIn("backup", scheduler.due(rome(2026, 11, 6, 2, 29), rome(2026, 11, 6, 2, 31)))
