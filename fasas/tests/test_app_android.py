"""App FASAS Signer distribuita dal FASAS: lettura dell'APK, pubblicazione, download con QR e avviso di versione.
Gli APK sono costruiti per il test (manifest binario minimo); la CI dell'app prova lo stesso lettore sull'APK vero."""
import io
import struct
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from fasas.signatures.apk import ApkError, parse_manifest, read_apk
from fasas.signatures.models import SignerAppRelease

from .base import FasasTestCase

ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _string_pool(strings):
    offsets, blob = [], b""
    for s in strings:
        offsets.append(len(blob))
        encoded = s.encode("utf-16-le")
        blob += struct.pack("<H", len(s)) + encoded + b"\0\0"
    blob += b"\0" * (-len(blob) % 4)
    header_size, count = 28, len(strings)
    body = struct.pack(f"<{count}I", *offsets) + blob
    return struct.pack("<HHIIIIII", 0x0001, header_size, header_size + len(body), count, 0, 0,
                       header_size + 4 * count, 0) + body


def _element(strings, name, attrs):
    """attrs: [(nome, tipo, valore)] con tipo "str", "int" o "bool"."""
    body = struct.pack("<iIHHHHHH", -1, strings.index(name), 20, 20, len(attrs), 0, 0, 0)
    for attr, kind, value in attrs:
        ns = strings.index(ANDROID_NS) if attr != "package" else -1
        if kind == "str":
            raw, dtype, data = strings.index(value), 0x03, strings.index(value)
        elif kind == "int":
            raw, dtype, data = -1, 0x10, value
        else:
            raw, dtype, data = -1, 0x12, 0xFFFFFFFF if value else 0
        body += struct.pack("<iIiHBBI", ns, strings.index(attr), raw, 8, 0, dtype, data)
    return struct.pack("<HHIII", 0x0102, 16, 16 + len(body), 1, 0xFFFFFFFF) + body


def manifest(package="it.fasas.signer.android", code=105, name="0.3.5", debuggable=False):
    strings = ["versionCode", "versionName", "debuggable", "android", ANDROID_NS, "package", "manifest",
               "application", name, package]
    resource_map = struct.pack("<HHI3I", 0x0180, 8, 20, 0x0101021B, 0x0101021C, 0x0101000F)
    chunks = _string_pool(strings) + resource_map
    chunks += _element(strings, "manifest", [("versionCode", "int", code), ("versionName", "str", name),
                                             ("package", "str", package)])
    chunks += _element(strings, "application", [("debuggable", "bool", True)] if debuggable else [])
    return struct.pack("<HHI", 0x0003, 8, 8 + len(chunks)) + chunks


def apk(**kwargs):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("AndroidManifest.xml", manifest(**kwargs))
        z.writestr("classes.dex", b"dex\n035\0")
    return buffer.getvalue()


class ApkReaderTests(FasasTestCase):
    def test_reads_package_version_and_debuggable(self):
        self.assertEqual(parse_manifest(manifest()), {"package": "it.fasas.signer.android", "versionCode": 105,
                                                      "versionName": "0.3.5", "debuggable": False})
        self.assertTrue(read_apk(io.BytesIO(apk(debuggable=True)))["debuggable"])

    def test_not_an_apk(self):
        with self.assertRaises(ApkError):
            read_apk(io.BytesIO(b"non sono uno zip"))
        with self.assertRaises(ApkError):
            parse_manifest(b"<manifest/>")


@override_settings(MEDIA_ROOT=__import__("tempfile").mkdtemp(prefix="fasas-test-app-"))
class AppDistributionTests(FasasTestCase):
    def upload(self, **kwargs):
        self.login(self.admin)
        return self.client.post(reverse("signatures:app_admin"), {
            "file": SimpleUploadedFile("app-release.apk", apk(**kwargs), "application/vnd.android.package-archive"),
            "notes": "Prima versione"})

    def test_admin_publishes_and_staff_downloads(self):
        self.upload()
        release = SignerAppRelease.latest()
        self.assertEqual((release.version_code, release.version_name, release.debuggable), (105, "0.3.5", False))
        self.login(self.operator)
        page = self.client.get(reverse("signatures:app_download"))
        self.assertContains(page, "<svg")  # QR code
        self.assertContains(page, release.sha256)
        anonymous = Client().get(reverse("signatures:app_apk"))
        self.assertEqual(anonymous.status_code, 200)
        self.assertEqual(anonymous["Content-Type"], "application/vnd.android.package-archive")
        self.assertEqual(b"".join(anonymous.streaming_content)[:2], b"PK")

    def test_refuses_other_apps_and_older_versions(self):
        self.upload(package="com.esempio.altra")
        self.assertFalse(SignerAppRelease.objects.exists())
        self.upload(code=105)
        response = self.upload(code=104)
        self.assertContains(response, "non è più recente")
        self.assertEqual(SignerAppRelease.objects.count(), 1)

    def test_debug_build_flagged(self):
        response = self.upload(debuggable=True)
        self.assertTrue(SignerAppRelease.latest().debuggable)
        self.assertEqual(response.status_code, 302)

    def test_version_info_for_the_app(self):
        url = reverse("signer_api:app_info")
        self.assertEqual(Client().get(url).json(), {"available": False})
        self.upload()
        data = Client().get(url).json()
        self.assertEqual((data["version_code"], data["version_name"]), (105, "0.3.5"))
        self.assertTrue(data["url"].endswith(reverse("signatures:app_apk")))

    def test_only_admin_publishes(self):
        self.login(self.coordinator)
        self.assertEqual(self.client.get(reverse("signatures:app_admin")).status_code, 403)
        self.assertEqual(Client().get(reverse("signatures:app_apk")).status_code, 404)
