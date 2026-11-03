"""
Lesioni da pressione e medicazioni: registrazione, foto cifrate senza EXIF, piano, scadenze, chiusura, permessi.
"""
import datetime
from io import BytesIO

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from fasas.core.jobs import run_job
from fasas.documents.models import Document
from fasas.documents.services import read_version
from fasas.notifications.models import Notification
from fasas.wounds import services
from fasas.wounds.models import Dressing, DressingPlan, Wound, WoundCheck

from .base import FasasTestCase


def jpeg(name="lesione.jpg", size=(3000, 1500), with_gps=True):
    image = Image.new("RGB", size, (180, 60, 60))
    buffer = BytesIO()
    exif = Image.Exif()
    if with_gps:
        exif[0x010F] = "TelefonoDiProva"  # marca
        exif[0x8825] = {1: "N", 2: (45.0, 30.0, 0.0)}  # GPS
    image.save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class WoundTestCase(FasasTestCase):
    def make_wound(self, **extra):
        data = {"kind": Wound.Kind.PRESSURE, "site": Wound.Site.SACRUM, "origin": Wound.Origin.IN_HOUSE,
                "stage": "2", "occurred_at": timezone.now() - datetime.timedelta(hours=1)}
        data.update(extra)
        return services.create_wound(self.guest, self.operator, **data)


class WoundServiceTests(WoundTestCase):
    def test_new_wound_notifies_coordinator_and_doctor(self):
        wound = self.make_wound(side=Wound.Side.LEFT, site=Wound.Site.HEEL)
        self.assertEqual(wound.site_display, "Tallone sinistra")
        self.assertTrue(wound.is_open)
        recipients = set(Notification.objects.filter(kind="wound_new").values_list("recipient__username", flat=True))
        self.assertEqual(recipients, {"coord", "doc"})

    def test_stage_only_for_pressure_ulcers(self):
        wound = self.make_wound(kind=Wound.Kind.SKIN_TEAR, site=Wound.Site.ARM, stage="3")
        self.assertEqual(wound.stage, "")
        check = services.add_check(wound, self.operator, stage="4", length_cm=2)
        self.assertEqual(check.stage, "")

    def test_future_and_archived_guest_refused(self):
        with self.assertRaisesMessage(services.WoundError, "futuro"):
            self.make_wound(occurred_at=timezone.now() + datetime.timedelta(hours=3))
        self.guest.status = "archived"
        self.guest.archived_at = timezone.now()
        self.guest.save()
        with self.assertRaisesMessage(services.WoundError, "archiviata"):
            self.make_wound()
        self.assertFalse(Wound.objects.exists())

    def test_photo_is_encrypted_resized_and_without_exif(self):
        wound = self.make_wound()
        check = services.add_check(wound, self.operator, stage="2", length_cm=3, width_cm=2, photo=jpeg())
        self.assertEqual(check.size_display, "3 × 2 cm")
        document = check.photo
        self.assertEqual(document.category, Document.Category.WOUND_PHOTO)
        data = read_version(document.current_version, self.operator)
        image = Image.open(BytesIO(data))
        self.assertEqual(image.format, "JPEG")
        self.assertLessEqual(max(image.size), services.PHOTO_MAX_SIDE)
        self.assertEqual(len(image.getexif()), 0)
        with default_storage.open(document.current_version.storage_name, "rb") as handle:
            raw = handle.read()
        self.assertFalse(raw.startswith(b"\xff\xd8"))  # sul disco non è un JPEG leggibile: è cifrata

    def test_fake_or_wrong_photo_refused(self):
        wound = self.make_wound()
        fake = SimpleUploadedFile("finta.jpg", b"non sono una foto", content_type="image/jpeg")
        with self.assertRaisesMessage(services.WoundError, "non è un'immagine"):
            services.add_check(wound, self.operator, photo=fake)
        buffer = BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, "GIF")
        gif = SimpleUploadedFile("foto.gif", buffer.getvalue(), content_type="image/gif")
        with self.assertRaisesMessage(services.WoundError, "JPEG o PNG"):
            services.add_check(wound, self.operator, photo=gif)
        self.assertFalse(WoundCheck.objects.exists())
        self.assertFalse(Document.objects.filter(category=Document.Category.WOUND_PHOTO).exists())

    def test_current_stage_follows_checks(self):
        wound = self.make_wound(stage="2")
        self.assertIn("Categoria 2", wound.current_stage)
        services.add_check(wound, self.operator, stage="3")
        services.add_check(wound, self.operator, length_cm=1)  # senza categoria: resta l'ultima indicata
        self.assertIn("Categoria 3", wound.current_stage)

    def test_new_plan_replaces_previous(self):
        wound = self.make_wound()
        first = services.set_plan(wound, self.coordinator, products="Idrocolloide", interval_days=3,
                                  indicated_by="Inf. Bianchi")
        second = services.set_plan(wound, self.coordinator, products="Schiuma di poliuretano", interval_days=2,
                                   indicated_by="Inf. Bianchi")
        first.refresh_from_db()
        self.assertFalse(first.active)
        self.assertEqual(first.ended_on, timezone.localdate())
        self.assertEqual(wound.active_plan, second)
        with self.assertRaisesMessage(services.WoundError, "tra 1 e 60"):
            services.set_plan(wound, self.coordinator, products="x", interval_days=0, indicated_by="x")

    def test_dressing_due_and_overdue(self):
        today = timezone.localdate()
        wound = self.make_wound(check_interval_days=0)
        self.assertEqual(services.due_list(today), [])
        services.set_plan(wound, self.coordinator, products="Idrocolloide", interval_days=3, indicated_by="Inf. B")
        row = services.due_list(today)[0]
        self.assertEqual((row["what"], row["due"], row["overdue"]), ("dressing", today, False))
        dressing = services.register_dressing(wound, self.operator)
        self.assertEqual(dressing.plan, wound.active_plan)
        self.assertEqual(services.due_list(today), [])
        self.assertEqual(services.due_list(today + datetime.timedelta(days=3))[0]["due"],
                         today + datetime.timedelta(days=3))
        late = services.due_list(today + datetime.timedelta(days=5))[0]
        self.assertTrue(late["overdue"])
        dressing.void(self.coordinator, "registrata per errore")
        self.assertEqual(services.due_list(today)[0]["what"], "dressing")  # l'annullata non conta

    def test_check_due_after_interval(self):
        today = timezone.localdate()
        wound = self.make_wound(check_interval_days=7)
        self.assertEqual(services.due_list(today), [])
        row = services.due_list(today + datetime.timedelta(days=8))[0]
        self.assertEqual((row["what"], row["overdue"]), ("check", True))
        services.add_check(wound, self.operator, length_cm=2)
        self.assertEqual(services.due_list(today + datetime.timedelta(days=6)), [])

    def test_reminders_once_and_job(self):
        wound = self.make_wound(check_interval_days=0)
        services.set_plan(wound, self.coordinator, products="Idrocolloide", interval_days=1, indicated_by="Inf. B",
                          start_date=timezone.localdate() - datetime.timedelta(days=2))
        self.assertEqual(services.due_reminders()["overdue"], 1)
        services.due_reminders()
        self.assertEqual(Notification.objects.filter(kind="dressing_due").count(), 1)
        self.assertIn("overdue", run_job("wounds"))

    def test_close_wound(self):
        wound = self.make_wound()
        plan = services.set_plan(wound, self.coordinator, products="Idrocolloide", interval_days=2,
                                 indicated_by="Inf. B")
        with self.assertRaisesMessage(services.WoundError, "motivo"):
            services.close_wound(wound, self.coordinator, Wound.Status.CLOSED)
        with self.assertRaisesMessage(services.WoundError, "precede"):
            services.close_wound(wound, self.coordinator, Wound.Status.HEALED,
                                 closed_at=wound.occurred_at - datetime.timedelta(days=1))
        services.close_wound(wound, self.coordinator, Wound.Status.HEALED, "riepitelizzata")
        plan.refresh_from_db()
        self.assertFalse(plan.active)
        self.assertEqual(services.due_list(), [])
        with self.assertRaisesMessage(services.WoundError, "chiusa"):
            services.register_dressing(wound, self.operator)


class WoundViewTests(WoundTestCase):
    def test_operator_flow(self):
        self.login(self.operator)
        url = reverse("wounds:create", args=[self.guest.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {
            "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "kind": "pressure", "site": "heel",
            "side": "right", "origin": "admission", "stage": "1", "check_interval_days": 7,
            "length_cm": "1.5", "width_cm": "1", "bed": "intact", "photo": jpeg(),
        })
        wound = Wound.objects.get()
        self.assertRedirects(response, wound.get_absolute_url())
        check = WoundCheck.objects.get()
        self.assertEqual((check.stage, check.bed), ("1", "intact"))
        self.assertIsNotNone(check.photo)
        page = self.client.get(wound.get_absolute_url())
        self.assertContains(page, "Tallone destra")
        self.assertContains(page, "1,5 × 1 cm")
        self.assertContains(page, reverse("documents:view", args=[check.photo.current_version.pk]))
        self.assertNotContains(page, reverse("wounds:plan", args=[wound.pk]))  # il piano lo indica chi è abilitato
        self.assertNotContains(page, reverse("wounds:close", args=[wound.pk]))
        response = self.client.post(reverse("wounds:dressing", args=[wound.pk]), {
            "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "notes": "cute integra intorno"})
        self.assertRedirects(response, wound.get_absolute_url())
        self.assertEqual(Dressing.objects.get().notes, "cute integra intorno")
        self.assertContains(self.client.get(reverse("wounds:guest", args=[self.guest.pk])), "Medicazione eseguita")

    def test_pressure_ulcer_requires_stage(self):
        self.login(self.operator)
        response = self.client.post(reverse("wounds:create", args=[self.guest.pk]), {
            "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "kind": "pressure", "site": "sacrum",
            "origin": "in_house", "check_interval_days": 7})
        self.assertContains(response, "Indicare la categoria")
        self.assertFalse(Wound.objects.exists())

    def test_wound_without_measures_has_no_check(self):
        self.login(self.operator)
        self.client.post(reverse("wounds:create", args=[self.guest.pk]), {
            "occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "kind": "skin_tear", "site": "arm",
            "origin": "in_house", "check_interval_days": 7})
        self.assertEqual(Wound.objects.count(), 1)
        self.assertFalse(WoundCheck.objects.exists())

    def test_check_form_and_bad_photo(self):
        wound = self.make_wound()
        self.login(self.operator)
        url = reverse("wounds:check", args=[wound.pk])
        self.assertContains(self.client.get(url), 'capture="environment"')
        fake = SimpleUploadedFile("x.jpg", b"testo", content_type="image/jpeg")
        response = self.client.post(url, {"occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                                          "stage": "3", "pain": 4, "photo": fake})
        self.assertContains(response, "non è un&#x27;immagine")
        response = self.client.post(url, {"occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                                          "stage": "3", "pain": 11})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WoundCheck.objects.exists())
        response = self.client.post(url, {"occurred_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                                          "stage": "3", "pain": 4, "infection_signs": "on"})
        self.assertRedirects(response, wound.get_absolute_url())
        self.assertContains(self.client.get(wound.get_absolute_url()), "segni di infezione")

    def test_coordinator_plan_due_quick_and_close(self):
        wound = self.make_wound(check_interval_days=0)
        self.login(self.coordinator)
        response = self.client.post(reverse("wounds:plan", args=[wound.pk]), {
            "products": "Detersione con fisiologica, idrocolloide", "procedure": "Proteggere la cute",
            "interval_days": 2, "start_date": timezone.localdate().isoformat(), "indicated_by": "Inf. Bianchi"})
        self.assertRedirects(response, wound.get_absolute_url())
        self.assertEqual(DressingPlan.objects.get().interval_days, 2)
        due = self.client.get(reverse("wounds:due"))
        self.assertContains(due, "Fatta adesso")
        response = self.client.post(reverse("wounds:dressing_quick", args=[wound.pk]))
        self.assertRedirects(response, reverse("wounds:due"))
        self.assertEqual(Dressing.objects.count(), 1)
        self.assertContains(self.client.get(reverse("wounds:due")), "Niente da fare oggi")
        page = self.client.get(reverse("wounds:plan", args=[wound.pk]))
        self.assertContains(page, "Detersione con fisiologica")  # proposto il piano in corso
        response = self.client.post(reverse("wounds:close", args=[wound.pk]), {
            "status": "healed", "closed_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"), "note": ""})
        self.assertRedirects(response, wound.get_absolute_url())
        wound.refresh_from_db()
        self.assertEqual(wound.status, Wound.Status.HEALED)
        self.assertEqual(self.client.get(reverse("wounds:close", args=[wound.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("wounds:guest", args=[self.guest.pk])), "Lesioni chiuse")

    def test_void_records(self):
        wound = self.make_wound()
        check = services.add_check(wound, self.operator, length_cm=1)
        dressing = services.register_dressing(wound, self.operator)
        self.login(self.coordinator)
        for name, obj in (("wounds:check_void", check), ("wounds:dressing_void", dressing), ("wounds:void", wound)):
            response = self.client.post(reverse(name, args=[obj.pk]), {"reason": "inserita sull'ospite sbagliato"})
            self.assertEqual(response.status_code, 302, name)
        self.assertFalse(Wound.objects.exists())
        self.assertTrue(Wound.all_objects.get(pk=wound.pk).is_voided)
        self.assertContains(self.client.get(reverse("wounds:detail", args=[wound.pk])), "annullata")

    def test_permissions(self):
        wound = self.make_wound()
        self.login(self.operator)
        for name in ("wounds:plan", "wounds:close", "wounds:void"):
            self.assertEqual(self.client.get(reverse(name, args=[wound.pk])).status_code, 403, name)
        administrative = self.make_user("amm", "administrative")
        self.login(administrative)
        self.assertEqual(self.client.get(reverse("wounds:guest", args=[self.guest.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("wounds:due")).status_code, 403)

    def test_pai_and_guest_folder(self):
        from fasas.pai.models import PAI
        from fasas.reports.guest_export import build_guest_folder

        wound = self.make_wound()
        services.add_check(wound, self.operator, stage="3", length_cm=2)
        services.set_plan(wound, self.coordinator, products="Schiuma", interval_days=2, indicated_by="Inf. B")
        services.register_dressing(wound, self.operator)
        pai = PAI.objects.create(guest=self.guest, version=1,
                                 review_due=timezone.localdate() + datetime.timedelta(days=180))
        self.login(self.coordinator)
        page = self.client.get(reverse("pai:detail", args=[pai.pk]))
        self.assertContains(page, "Lesioni aperte")
        self.assertContains(page, "Categoria 3")
        self.assertTrue(build_guest_folder(self.guest, self.coordinator).startswith(b"%PDF"))
        from fasas.reports.pdf import pai_pdf

        self.assertTrue(pai_pdf(pai).startswith(b"%PDF"))
