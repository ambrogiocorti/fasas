"""Impostazioni prudenti per il pilota: avvio di prova, firma spenta o nascosta, avviso delle chiavi pubbliche."""
import io
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import override_settings
from django.urls import reverse

from fasas.core.management.commands.fasas_demo import GUESTS

from .base import FasasTestCase


class TrialLauncherCheckTests(FasasTestCase):
    def test_only_demo_guests_starts(self):
        self.guest.delete()
        self.make_guest(fiscal_code=GUESTS[0][4])
        out = io.StringIO()
        call_command("fasas_controllo_prova", stdout=out)
        self.assertIn("solo gli ospiti dimostrativi", out.getvalue())

    def test_real_guests_stop_the_trial_without_confirmation(self):
        err = io.StringIO()
        with mock.patch("sys.stdin.isatty", return_value=False), self.assertRaises(CommandError):
            call_command("fasas_controllo_prova", stderr=err)
        self.assertIn("1 ospiti che non sono quelli dimostrativi", err.getvalue())

    def test_typed_confirmation_is_required(self):
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="si"):
            with self.assertRaises(CommandError):
                call_command("fasas_controllo_prova", stderr=io.StringIO())
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="dati di fantasia"):
            call_command("fasas_controllo_prova", stderr=io.StringIO())
        call_command("fasas_controllo_prova", "--conferma-dati-di-fantasia", stderr=io.StringIO())


class DevKeysBannerTests(FasasTestCase):
    @override_settings(FASAS_DEV_KEYS_IN_USE=True)
    def test_banner_on_every_page_and_login(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "dev-keys-banner")
        self.login(self.coordinator)
        self.assertContains(self.client.get("/"), "Installazione di prova")

    @override_settings(FASAS_DEV_KEYS_IN_USE=False)
    def test_no_banner_with_real_keys(self):
        self.login(self.coordinator)
        self.assertNotContains(self.client.get("/"), "dev-keys-banner")


class SignatureVisibilityTests(FasasTestCase):
    def setUp(self):
        self.login(self.doctor)

    @override_settings(FASAS_CSC_SERVICE_URL="")
    def test_remote_signature_hidden_until_configured(self):
        page = self.client.get(reverse("signatures:credential"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="remota"')
        self.assertNotContains(page, "Firma remota del prestatore")

    @override_settings(FASAS_CSC_SERVICE_URL="https://csc.esempio.invalid/csc/v1")
    def test_remote_signature_shown_when_configured(self):
        self.assertContains(self.client.get(reverse("signatures:credential")), 'id="remota"')

    @override_settings(FASAS_CIE_ENABLED=False)
    def test_cie_hidden_when_disabled(self):
        page = self.client.get(reverse("signatures:credential"))
        self.assertContains(page, "non attiva nella struttura")
        self.assertNotContains(page, 'id="cie"')
        self.assertNotContains(self.client.get(reverse("documents:to_sign")), "Firma con CIE</a>")
