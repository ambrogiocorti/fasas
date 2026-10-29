"""
Firma con CIE (FASAS Sign): ciclo di vita, sicurezza e motore PAdES a firma esterna.

Le «carte» sono chiavi e certificati di prova (vedi cie_helpers): le firme sono crittograficamente reali
ma non sono firme con CIE. Il test con PKCS#11 reale (SoftHSM) è in test_cie_signer_pkcs11.
"""
import base64
import datetime

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from fasas.accounts.models import Role
from fasas.audit.models import AuditLog
from fasas.documents.models import Document
from fasas.documents.services import DocumentLockedError, add_uploaded_version, create_document, read_version
from fasas.signatures import cie
from fasas.signatures.models import LegalLevel, Signature, SignatureRequest, SignerDevice
from fasas.signatures.providers import SignatureError, verify_pdf

from .base import FasasTestCase
from .cie_helpers import DeviceClient, TestPKI
from .test_documents import sample_pdf

PKI = TestPKI()
OTHER_PKI = TestPKI("Altra")
DOCTOR_CF = "BNCLRA80A41H501Y"
COORD_CF = "VRDGPP75C10F205K"


@override_settings(**PKI.settings())
class CIESignatureTests(FasasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.doctor.fiscal_code = DOCTOR_CF
        cls.doctor.save()
        cls.coordinator.fiscal_code = COORD_CF
        cls.coordinator.save()
        cls.card = PKI.card(DOCTOR_CF)
        cls.coord_card = PKI.card(COORD_CF, "Giuseppe", "Verdi")

    def setUp(self):
        cache.clear()
        self.document = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione clinica",
                                        user=self.doctor, data=sample_pdf(), filename="relazione.pdf")
        self.version = self.document.current_version
        self.device = self.paired(self.doctor)

    def paired(self, user, name="PC ambulatorio"):
        device = DeviceClient(self.client_class())
        status, data = device.pair(cie.create_pairing(user), name)
        self.assertEqual(status, 201, data)
        return device

    def start(self, user=None, version=None):
        return cie.create_request(version or self.version, user or self.doctor, "Relazione da firmare")

    def denied(self):
        return AuditLog.objects.filter(action=AuditLog.Action.DENIED)

    # 1. Firma riuscita: nuova versione firmata, FEA, PAdES verificabile, originale intatto
    def test_successful_signature(self):
        self.login(self.doctor)
        page = self.client.get(reverse("documents:sign_cie", args=[self.version.pk]))
        self.assertContains(page, 'class="pdf-frame"')
        self.assertContains(page, reverse("documents:view", args=[self.version.pk]))
        response = self.client.post(reverse("documents:sign_cie", args=[self.version.pk]),
                                    {"reason": "Approvazione", "confirm": "on"})
        request = SignatureRequest.objects.get()
        self.assertRedirects(response, reverse("signatures:cie_request", args=[request.pk]))
        status, pending = self.device.get("richieste/")
        self.assertEqual([r["verify_code"] for r in pending["requests"]], [request.verify_code])
        self.assertEqual(pending["requests"][0]["document_sha256"], self.version.sha256)
        status, data = self.device.sign_flow(request.pk, self.card)
        self.assertEqual((status, data["status"]), (200, "signed"), data)
        self.assertEqual(data["verification"], {"intact": True, "valid": True, "trusted": True, "level": "PAdES-B-B",
                                                "timestamped": False})
        signature = Signature.objects.get()
        self.assertEqual((signature.provider, signature.legal_level, signature.signature_format),
                         ("cie", LegalLevel.FEA, "PAdES-B-B"))
        self.assertIn(DOCTOR_CF, signature.certificate_subject)
        signed = read_version(signature.signed_version)
        self.assertTrue(signed.startswith(read_version(self.version)))
        [result] = verify_pdf(signed)
        self.assertTrue(result["intact"] and result["valid"] and result["trusted"] and result["covers_whole_document"])
        self.assertFalse(result["qualified_statements"])
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.SIGN, object_id=str(signature.signed_version.pk))
                        .exists())
        state = self.client.get(reverse("signatures:cie_status", args=[request.pk])).json()
        self.assertEqual((state["status"], state["document_state"], state["version"]), ("signed", "FIRMATO", 2))
        detail = self.client.get(self.document.get_absolute_url())
        self.assertContains(detail, "Firma elettronica avanzata")
        request.refresh_from_db()
        self.assertEqual(request.prepared_storage, "")  # il PDF preparato non resta sul server

    # 2. Meccanismo alternativo: CKM_RSA_PKCS sul DigestInfo dà la stessa firma valida
    def test_digest_info_mechanism(self):
        request = self.start()
        status, data = self.device.sign_flow(request.pk, self.card, mechanism="digest_info")
        self.assertEqual(data["status"], "signed", data)

    # 3. Firme multiple: la seconda firma non invalida la prima
    def test_multiple_signatures(self):
        self.device.sign_flow(self.start().pk, self.card)
        signed_version = self.document.current_version
        coordinator_device = self.paired(self.coordinator, "PC coordinamento")
        status, data = coordinator_device.sign_flow(self.start(self.coordinator, signed_version).pk, self.coord_card)
        self.assertEqual(data["status"], "signed", data)
        results = verify_pdf(read_version(self.document.current_version))
        self.assertEqual([r["field"] for r in results], ["FirmaFASAS1", "FirmaFASAS2"])
        self.assertTrue(all(r["intact"] and r["valid"] and r["trusted"] for r in results))
        self.assertEqual(self.document.versions.count(), 3)

    # 4. La carta di un'altra persona viene rifiutata e il tentativo registrato
    def test_card_of_another_person(self):
        request = self.start()
        status, data = self.device.sign_flow(request.pk, PKI.card("RSSMRA80A01H501U", "Mario", "Rossi"))
        self.assertEqual((status, data["error"]), (400, "cert_mismatch"))
        request.refresh_from_db()
        self.assertEqual(request.status, "failed")
        self.assertTrue(self.denied().filter(changes__codice=[None, "cert_mismatch"]).exists())
        self.assertEqual(self.document.versions.count(), 1)

    # 5. Certificato scaduto e 6. certificato non emesso dalla CA configurata
    def test_expired_and_untrusted_certificates(self):
        status, data = self.device.sign_flow(self.start().pk, PKI.card(DOCTOR_CF, days=(-400, -1)))
        self.assertEqual(data["error"], "cert_expired")
        status, data = self.device.sign_flow(self.start().pk, OTHER_PKI.card(DOCTOR_CF))
        self.assertEqual(data["error"], "cert_untrusted")
        self.assertFalse(Signature.objects.exists())

    # 7. Un valore di firma che non corrisponde al documento preparato viene rifiutato
    def test_wrong_signature_value(self):
        request = self.start()
        _, claimed = self.device.post(f"richieste/{request.pk}/prendi/")
        _, prepared = self.device.post(f"richieste/{request.pk}/certificato/",
                                       {"nonce": claimed["nonce"], "certificate": self.card.der_b64})
        forged = self.card.sign(base64.b64encode(b"altro contenuto").decode())
        status, data = self.device.post(f"richieste/{request.pk}/firma/", {"nonce": prepared["nonce"], "signature": forged})
        self.assertEqual((status, data["error"]), (400, "bad_signature"))
        request.refresh_from_db()
        self.assertEqual(request.status, "failed")
        self.assertFalse(Signature.objects.exists())

    # 8. Replay: un nonce già usato non è più accettato, nemmeno a firma conclusa
    def test_replay_is_rejected(self):
        request = self.start()
        _, claimed = self.device.post(f"richieste/{request.pk}/prendi/")
        _, prepared = self.device.post(f"richieste/{request.pk}/certificato/",
                                       {"nonce": claimed["nonce"], "certificate": self.card.der_b64})
        status, data = self.device.post(f"richieste/{request.pk}/certificato/",
                                        {"nonce": claimed["nonce"], "certificate": self.card.der_b64})
        self.assertEqual((status, data["error"]), (409, "bad_nonce"))
        signature = self.card.sign(prepared["to_be_signed"])
        status, data = self.device.post(f"richieste/{request.pk}/firma/", {"nonce": prepared["nonce"], "signature": signature})
        self.assertEqual(data["status"], "signed")
        status, data = self.device.post(f"richieste/{request.pk}/firma/", {"nonce": prepared["nonce"], "signature": signature})
        self.assertEqual(status, 409)
        self.assertEqual(Signature.objects.count(), 1)
        self.assertGreaterEqual(self.denied().filter(changes__codice=[None, "bad_nonce"]).count(), 2)

    # 9. IDOR: né un altro dispositivo né un altro utente vedono o toccano la richiesta
    def test_other_users_cannot_access(self):
        request = self.start()
        intruder = self.paired(self.coordinator, "PC altrui")
        self.assertEqual(intruder.get("richieste/")[1]["requests"], [])
        status, data = intruder.post(f"richieste/{request.pk}/prendi/")
        self.assertEqual((status, data["error"]), (404, "not_found"))
        self.login(self.coordinator)
        self.assertEqual(self.client.get(reverse("signatures:cie_status", args=[request.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("signatures:cie_cancel", args=[request.pk])).status_code, 404)
        # Secondo dispositivo dello stesso medico: dopo la presa in carico la richiesta è di un solo dispositivo
        second = self.paired(self.doctor, "Portatile")
        self.device.post(f"richieste/{request.pk}/prendi/")
        self.assertEqual(second.post(f"richieste/{request.pk}/prendi/")[1]["error"], "wrong_device")
        self.assertGreaterEqual(self.denied().count(), 3)
        # Chi non ha il permesso non apre la pagina di firma
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse("documents:sign_cie", args=[self.version.pk])).status_code, 403)

    # 10. Versione bloccata durante la firma; 11. niente richieste duplicate
    def test_version_lock_and_no_duplicates(self):
        request = self.start()
        self.assertEqual(self.start().pk, request.pk)  # stessa richiesta, non un duplicato
        with self.assertRaises(SignatureError) as ctx:
            self.start(self.coordinator)
        self.assertEqual(ctx.exception.code, "locked")
        upload = SimpleUploadedFile("nuova.pdf", sample_pdf(), content_type="application/pdf")
        with self.assertRaises(DocumentLockedError):
            add_uploaded_version(self.document, upload, self.doctor)
        self.login(self.doctor)
        self.assertContains(self.client.get(self.document.get_absolute_url()), "bloccata fino alla conclusione")
        cie.cancel_request(request, self.doctor)
        upload.seek(0)
        add_uploaded_version(self.document, upload, self.doctor)
        with self.assertRaises(SignatureError):  # la versione firmabile è solo l'ultima
            self.start()

    # 12. Scadenza della richiesta
    def test_expiry(self):
        request = self.start()
        SignatureRequest.objects.filter(pk=request.pk).update(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        status, data = self.device.post(f"richieste/{request.pk}/prendi/")
        self.assertEqual((status, data["error"]), (410, "expired"))
        request.refresh_from_db()
        self.assertEqual(request.status, "expired")
        self.assertEqual(self.device.get("richieste/")[1]["requests"], [])

    # 13. Annullamento e nuovo tentativo: nuova richiesta, mai riuso della precedente
    def test_cancel_and_retry(self):
        self.login(self.doctor)
        request = self.start()
        self.client.post(reverse("signatures:cie_cancel", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, "cancelled")
        self.assertEqual(self.device.post(f"richieste/{request.pk}/prendi/")[0], 409)
        response = self.client.post(reverse("signatures:cie_retry", args=[request.pk]))
        retry = SignatureRequest.objects.get(previous=request)
        self.assertRedirects(response, reverse("signatures:cie_request", args=[retry.pk]))
        self.assertEqual((retry.attempt, retry.status), (2, "waiting"))
        self.assertNotEqual(retry.verify_code, request.verify_code)
        self.client.post(reverse("signatures:cie_retry", args=[request.pk]))
        self.assertEqual(SignatureRequest.objects.count(), 2)
        self.assertEqual(self.device.sign_flow(retry.pk, self.card)[1]["status"], "signed")

    # 14. Errori del dispositivo: carta assente, PIN errato con tentativi rimasti, PIN bloccato, carta rimossa
    def test_device_errors(self):
        request = self.start()
        _, data = self.device.post(f"richieste/{request.pk}/prendi/")
        _, data = self.device.post(f"richieste/{request.pk}/stato/", {"nonce": data["nonce"], "state": "card_missing"})
        self.login(self.doctor)
        state = self.client.get(reverse("signatures:cie_status", args=[request.pk])).json()
        self.assertEqual((state["status"], state["error_code"]), ("waiting", "card_absent"))
        _, data = self.device.post(f"richieste/{request.pk}/certificato/", {"nonce": data["nonce"],
                                                                            "certificate": self.card.der_b64})
        _, data = self.device.post(f"richieste/{request.pk}/stato/", {"nonce": data["nonce"], "state": "pin_wrong",
                                                                      "attempts_left": 2})
        state = self.client.get(reverse("signatures:cie_status", args=[request.pk])).json()
        self.assertEqual((state["status"], state["error_code"], state["pin_attempts_left"]), ("authorizing", "pin_wrong", 2))
        _, data = self.device.post(f"richieste/{request.pk}/errore/", {"nonce": data["nonce"], "code": "pin_blocked"})
        self.assertEqual(data, {"status": "failed", "error": "pin_blocked"})
        state = self.client.get(reverse("signatures:cie_status", args=[request.pk])).json()
        self.assertIn("PUK", state["error"])
        other = self.start()
        _, data = self.device.post(f"richieste/{other.pk}/prendi/")
        _, data = self.device.post(f"richieste/{other.pk}/errore/", {"nonce": data["nonce"], "code": "qualsiasi testo"})
        self.assertEqual(data["error"], "device_error")  # niente testo libero dal dispositivo

    # 15. Abbinamento: codice monouso e a scadenza, token revocabile, limite di tentativi
    def test_pairing_and_revocation(self):
        code = cie.create_pairing(self.doctor)
        self.assertEqual(DeviceClient(self.client_class()).pair(code)[0], 201)
        self.assertEqual(DeviceClient(self.client_class()).pair(code)[0], 400)  # già usato
        device = SignerDevice.objects.filter(user=self.doctor).first()
        self.assertNotIn(self.device.token, str(SignerDevice.objects.values_list("token_hash", flat=True)))
        cie.revoke_device(SignerDevice.objects.get(token_hash=cie._hash(self.device.token)), self.doctor)
        self.assertEqual(self.device.get("richieste/")[0], 401)
        self.assertIsNotNone(device)
        intruder = DeviceClient(self.client_class())
        for _ in range(10):
            intruder.pair("AAAA-BBBB")
        self.assertEqual(intruder.pair("AAAA-BBBB")[0], 429)
        self.assertTrue(self.denied().filter(changes__codice=[None, "pairing_invalid"]).exists())
        self.assertEqual(DeviceClient(self.client_class(), "token-inventato").get("richieste/")[0], 401)

    # 16. Prova di funzionamento con documento senza dati sanitari
    def test_test_signature(self):
        self.login(self.doctor)
        response = self.client.post(reverse("signatures:cie_test"))
        request = SignatureRequest.objects.get(purpose="test")
        self.assertRedirects(response, reverse("signatures:cie_request", args=[request.pk]))
        preview = self.client.get(reverse("signatures:cie_test_file", args=[request.pk]))
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(self.device.sign_flow(request.pk, self.card)[1]["status"], "signed")
        signed = self.client.get(reverse("signatures:cie_test_file", args=[request.pk]) + "?firmato=1")
        self.assertIn("attachment", signed["Content-Disposition"])
        self.assertTrue(verify_pdf(signed.content)[0]["trusted"])
        self.assertFalse(Signature.objects.exists())  # la prova non crea documenti
        self.assertContains(self.client.get(reverse("signatures:credential")), "catena verificata")

    # 17. Solo HTTPS in produzione e firma bloccata senza le CA della CIE
    def test_https_and_trust_required(self):
        with override_settings(FASAS_CIE_ALLOW_HTTP=False):
            self.assertEqual(self.device.get("richieste/")[0], 403)
        with override_settings(FASAS_CIE_TRUST_ROOTS=""):
            with self.assertRaises(SignatureError) as ctx:
                self.start()
            self.assertEqual(ctx.exception.code, "trust_not_configured")

    # 18. Niente PIN né contenuti del documento verso il server o nei registri
    def test_no_pin_and_no_document_content_in_logs(self):
        request = self.start()
        with self.assertLogs("fasas", level="DEBUG") as logs:
            import logging

            logging.getLogger("fasas").debug("inizio")
            _, claimed = self.device.post(f"richieste/{request.pk}/prendi/")
            _, prepared = self.device.post(f"richieste/{request.pk}/certificato/", {
                "nonce": claimed["nonce"], "certificate": self.card.der_b64, "pin": "97531864"})
            self.device.post(f"richieste/{request.pk}/firma/", {"nonce": prepared["nonce"],
                                                                "signature": self.card.sign(prepared["to_be_signed"])})
        text = " ".join(logs.output) + str(list(AuditLog.objects.values_list("changes", "reason", "object_repr")))
        for secret in ("97531864", "Contenuto sanitario", base64.b64encode(read_version(self.version))[:40].decode()):
            self.assertNotIn(secret, text)
        self.assertFalse(any("pin" in f.name for f in SignatureRequest._meta.fields if f.name != "pin_attempts_left"))

    def test_tampering_is_detected(self):
        self.device.sign_flow(self.start().pk, self.card)
        signed = bytearray(read_version(self.document.current_version))
        position = signed.index(b"Contenuto") if b"Contenuto" in signed else 200
        signed[position] ^= 0x01
        self.assertFalse(verify_pdf(bytes(signed))[0]["intact"])

    def test_settings_page_and_admin_devices(self):
        self.login(self.doctor)
        page = self.client.get(reverse("signatures:credential"))
        for text in ("Firma con CIE", "Firma elettronica avanzata", "Firma elettronica qualificata",
                     "Firma elettronica non qualificata", "Approvazioni interne", "PC ambulatorio"):
            self.assertContains(page, text)
        self.client.post(reverse("signatures:credential"), {"action": "cie-pair"})
        page = self.client.get(reverse("signatures:credential"))
        self.assertContains(page, "Codice di abbinamento")
        self.assertNotContains(self.client.get(reverse("signatures:credential")), "Codice di abbinamento")
        self.login(self.coordinator)  # firma solo con CIE: niente certificato personale né firma remota
        page = self.client.get(reverse("signatures:credential"))
        self.assertContains(page, "Abbina un nuovo FASAS Signer")
        self.assertNotContains(page, "Registra certificato")
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("signatures:devices")), "PC ambulatorio")
        device = SignerDevice.objects.get(name="PC ambulatorio")
        self.client.post(reverse("signatures:devices"), {"device": device.pk})
        device.refresh_from_db()
        self.assertIsNotNone(device.revoked_at)
        self.assertEqual(self.client.get(reverse("signatures:credential")).status_code, 403)

    def test_device_status_report(self):
        status, data = self.device.post("dispositivo/stato/", {
            "middleware_found": True, "middleware": "libcie-pkcs11.so 1.5", "readers": ["ACS ACR1252"],
            "card_present": True, "nome_ospite": "da scartare"})
        self.assertEqual(status, 200)
        self.assertNotIn("nome_ospite", data["status"])
        self.login(self.doctor)
        self.assertContains(self.client.get(reverse("signatures:credential")), "ACS ACR1252")


class CertificateParsingTests(FasasTestCase):
    def test_fiscal_code_sources_and_chip_padding(self):
        from asn1crypto import x509 as ax509
        from cryptography.hazmat.primitives.serialization import Encoding

        from fasas.signatures import external
        from fasas.tests.cie_helpers import _build, _key, _name

        der = PKI.card(DOCTOR_CF).cert.public_bytes(Encoding.DER)
        self.assertEqual(external.fiscal_codes_in(external.load_certificate(der + bytes(300))), {DOCTOR_CF})
        with self.assertRaises(SignatureError):
            external.load_certificate(der + b"\x01")  # dati estranei (non zeri) dopo il certificato
        key = _key()
        qualified = _build(_name(cn="Laura Bianchi", serial=f"TINIT-{DOCTOR_CF}"), _name(cn="CA"), key.public_key(), key)
        self.assertEqual(external.fiscal_codes_in(ax509.Certificate.load(qualified.public_bytes(Encoding.DER))),
                         {DOCTOR_CF})
        elsewhere = _build(_name(cn="Laura Bianchi", o=DOCTOR_CF), _name(cn="CA"), key.public_key(), key)
        self.assertEqual(external.fiscal_codes_in(ax509.Certificate.load(elsewhere.public_bytes(Encoding.DER))), set())


class LegalLevelTests(FasasTestCase):
    def test_personal_certificate_is_never_qualified(self):
        from fasas.signatures.services import register_pkcs12, sign_version

        from .test_documents import self_signed_p12

        document = create_document(self.guest, Document.Category.MEDICAL_REPORT, "Relazione", user=self.doctor,
                                   data=sample_pdf(), filename="r.pdf")
        register_pkcs12(self.doctor, self_signed_p12("segreta"), "segreta")
        signature = sign_version(document.current_version, self.doctor, "segreta")
        self.assertEqual(signature.legal_level, LegalLevel.FE)

    def test_role_permissions(self):
        self.assertTrue(self.doctor.has_perm("signatures.sign_with_cie"))
        self.assertTrue(self.coordinator.has_perm("signatures.sign_with_cie"))
        for user in (self.operator, self.admin, self.make_user("amm", Role.ADMINISTRATIVE)):
            self.assertFalse(user.has_perm("signatures.sign_with_cie"), user.username)
        self.assertTrue(self.admin.has_perm("signatures.manage_signer_devices"))
