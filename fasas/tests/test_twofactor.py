"""Verifica in due passaggi (TOTP): obbligatoria per i ruoli sensibili, codici monouso, blocco, recupero, API."""
import base64

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from fasas.accounts import twofactor
from fasas.accounts.models import AccessLog, RecoveryCode, TwoFactorDevice
from fasas.audit.models import AuditLog

from .base import PASSWORD, FasasTestCase

LOGIN = "/accesso/entra/"


class TotpTests(FasasTestCase):
    def test_rfc6238_reference_vectors(self):
        secret = base64.b32encode(b"12345678901234567890").decode()  # SHA-1, appendice B dell'RFC 6238
        self.assertEqual(twofactor.code_at(secret, twofactor.current_step(59)), "287082")
        self.assertEqual(twofactor.code_at(secret, twofactor.current_step(1111111109)), "081804")
        self.assertEqual(twofactor.code_at(secret, twofactor.current_step(2000000000)), "279037")
        step = twofactor.current_step(1111111109)
        self.assertEqual(twofactor.matching_step(secret, "081 804", now=1111111109), step)
        self.assertEqual(twofactor.matching_step(secret, twofactor.code_at(secret, step + 1), now=1111111109), step + 1)
        self.assertIsNone(twofactor.matching_step(secret, twofactor.code_at(secret, step + 2), now=1111111109))
        self.assertIsNone(twofactor.matching_step(secret, "12345", now=1111111109))

    def test_provisioning_uri_and_qr(self):
        uri = twofactor.provisioning_uri("JBSWY3DPEHPK3PXP", "doc")
        self.assertTrue(uri.startswith("otpauth://totp/FASAS%3Adoc?secret=JBSWY3DPEHPK3PXP&issuer=FASAS"))
        self.assertIn("<svg", twofactor.qr_svg(uri))


class TwoFactorLoginTests(FasasTestCase):
    def login_password(self, username, **extra):
        return self.client.post(LOGIN, {"username": username, "password": PASSWORD}, **extra)

    def enroll(self, username="doc"):
        """Primo accesso di un medico: password, QR code, primo codice, codici di recupero."""
        response = self.login_password(username)
        self.assertRedirects(response, reverse("accounts:otp_setup"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/"), f"{LOGIN}?next=/", fetch_redirect_response=False)  # non ancora dentro
        page = self.client.get(reverse("accounts:otp_setup"))
        self.assertContains(page, "<svg")
        self.assertContains(page, "obbligatoria")
        secret = self.client.session[twofactor.SESSION_SETUP]
        wrong = self.client.post(reverse("accounts:otp_setup"), {"code": "000000"})
        self.assertContains(wrong, "Codice non valido")
        done = self.client.post(reverse("accounts:otp_setup"),
                                {"code": twofactor.code_at(secret, twofactor.current_step())})
        self.assertContains(done, "salva i codici di recupero")
        codes = done.context["codes"]
        self.assertEqual(len(codes), 10)
        self.assertEqual(self.client.get("/").status_code, 200)  # ora è dentro
        return secret, codes

    def test_doctor_must_enroll_then_verify_every_time(self):
        secret, codes = self.enroll()
        device = TwoFactorDevice.objects.get(user=self.doctor)
        self.assertNotIn(secret.encode(), bytes(device.secret))  # segreto cifrato
        self.assertEqual(twofactor.decrypt_secret(device.secret), secret)
        self.assertFalse(RecoveryCode.objects.filter(code_hash__in=codes).exists())  # solo impronte
        self.assertTrue(AuditLog.objects.filter(action="permission", object_id=str(self.doctor.pk),
                                                changes__icontains="attivata").exists())
        self.client.post(reverse("accounts:logout"))

        self.assertRedirects(self.login_password("doc"), reverse("accounts:otp_verify"), fetch_redirect_response=False)
        same = twofactor.code_at(secret, device.last_step)  # già usato all'attivazione: non vale due volte
        self.assertContains(self.client.post(reverse("accounts:otp_verify"), {"code": same}), "già usato")
        self.assertTrue(AccessLog.objects.filter(username="doc", event=AccessLog.Event.OTP_FAILED).exists())
        response = self.client.post(reverse("accounts:otp_verify"),
                                    {"code": twofactor.code_at(secret, device.last_step + 1)})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(AccessLog.objects.filter(username="doc", event=AccessLog.Event.LOGIN).count(), 2)

    def test_recovery_code_works_once(self):
        _, codes = self.enroll()
        self.client.post(reverse("accounts:logout"))
        self.login_password("doc")
        response = self.client.post(reverse("accounts:otp_verify"), {"code": codes[0].upper()}, follow=True)
        self.assertContains(response, "ne restano 9")
        self.client.post(reverse("accounts:logout"))
        self.login_password("doc")
        self.assertContains(self.client.post(reverse("accounts:otp_verify"), {"code": codes[0]}), "Codice non valido")

    def test_wrong_codes_lock_the_account(self):
        self.enroll()
        self.client.post(reverse("accounts:logout"))
        self.login_password("doc")
        for _ in range(5):
            self.client.post(reverse("accounts:otp_verify"), {"code": "123456"})
        response = self.client.post(reverse("accounts:otp_verify"), {"code": "123456"}, follow=True)
        self.assertContains(response, "Troppi tentativi")
        self.assertTrue(AccessLog.objects.filter(username="doc", event=AccessLog.Event.LOCKED).exists())
        self.assertContains(self.login_password("doc"), "Troppi tentativi")  # anche la password ora è bloccata

    def test_pending_login_expires(self):
        self.login_password("doc")
        session = self.client.session
        session[twofactor.SESSION_PENDING]["at"] -= twofactor.PENDING_SECONDS + 1
        session.save()
        self.assertRedirects(self.client.get(reverse("accounts:otp_verify")), LOGIN, fetch_redirect_response=False)

    def test_operator_logs_in_directly_and_may_enable_it(self):
        self.assertRedirects(self.login_password("oper"), "/", fetch_redirect_response=False)
        page = self.client.get(reverse("accounts:security"))
        self.assertContains(page, "non attiva")
        self.assertNotContains(page, "obbligatoria per il tuo ruolo")
        self.client.get(reverse("accounts:otp_setup"))
        secret = self.client.session[twofactor.SESSION_SETUP]
        step = twofactor.current_step()
        self.client.post(reverse("accounts:otp_setup"), {"code": twofactor.code_at(secret, step)})
        self.assertTrue(TwoFactorDevice.objects.filter(user=self.operator).exists())
        codes = self.client.post(reverse("accounts:security"),
                                 {"code": twofactor.code_at(secret, step + 1), "action": "codes"})
        self.assertEqual(len(codes.context["codes"]), 10)
        self.client.post(reverse("accounts:security"), {"code": codes.context["codes"][0], "action": "disable"})
        self.assertFalse(TwoFactorDevice.objects.filter(user=self.operator).exists())
        self.assertFalse(RecoveryCode.objects.filter(user=self.operator).exists())

    @override_settings(FASAS_2FA_TRUSTED_NETWORKS=["10.20.0.0/16"])
    def test_outside_the_structure_network(self):
        inside = {"REMOTE_ADDR": "10.20.1.5"}
        self.assertRedirects(self.login_password("oper", **inside), "/", fetch_redirect_response=False)
        self.client.post(reverse("accounts:logout"))
        # da fuori: anche l'operatore deve usare la verifica, ma non può attivarla con la sola password
        self.assertContains(self.login_password("oper", REMOTE_ADDR="203.0.113.7"), "fuori dalla rete")
        self.assertContains(self.login_password("doc", REMOTE_ADDR="203.0.113.7"), "fuori dalla rete")
        self.assertRedirects(self.login_password("doc", **inside), reverse("accounts:otp_setup"),
                             fetch_redirect_response=False)

    def test_admin_resets_lost_phone(self):
        self.enroll()
        self.client.post(reverse("accounts:logout"))
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("accounts:user_list")), "Reimposta")
        response = self.client.post(reverse("accounts:user_reset_2fa", args=[self.doctor.pk]), follow=True)
        self.assertContains(response, "reimpostata")
        self.assertFalse(TwoFactorDevice.objects.filter(user=self.doctor).exists())
        self.assertTrue(AuditLog.objects.filter(user=self.admin, object_id=str(self.doctor.pk),
                                                changes__icontains="reimpostata").exists())
        self.login(self.operator)
        self.client.post(reverse("accounts:user_reset_2fa", args=[self.admin.pk]))
        self.assertTrue(AuditLog.objects.filter(changes__icontains="reimpostata").count() == 1)

    def test_technical_admin_area_has_no_separate_login(self):
        response = self.client.get("/gestione-tecnica/")
        self.assertIn(LOGIN, response.url if response.status_code == 302 else self.client.get(response.url).url)

    @override_settings(FASAS_2FA_REQUIRED_ROLES=[])
    def test_roles_can_be_made_optional(self):
        self.assertRedirects(self.login_password("doc"), "/", fetch_redirect_response=False)


class TwoFactorApiTests(FasasTestCase):
    def test_token_requires_the_code(self):
        api = APIClient()
        self.assertEqual(api.post("/api/v1/token/", {"username": "doc", "password": PASSWORD}).status_code, 403)
        secret = twofactor.new_secret()
        step = twofactor.current_step()
        twofactor.enroll(self.doctor, secret, twofactor.code_at(secret, step))
        self.assertEqual(api.post("/api/v1/token/", {"username": "doc", "password": PASSWORD}).status_code, 403)
        ok = api.post("/api/v1/token/", {"username": "doc", "password": PASSWORD,
                                         "otp": twofactor.code_at(secret, step + 1)})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertIn("token", ok.json())
        self.assertEqual(api.post("/api/v1/token/", {"username": "oper", "password": PASSWORD}).status_code, 200)
