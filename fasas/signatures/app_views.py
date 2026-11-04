"""
App FASAS Signer per Android distribuita dal FASAS stesso: l'amministratore carica l'APK firmato con la chiave della
struttura, il personale lo scarica dalla pagina «App per il telefono» (QR code dal computer) e l'app avvisa quando
c'è una versione più recente. Niente GitHub per gli operatori.
"""
import hashlib

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event

from .apk import ApkError, read_apk
from .models import SignerAppRelease

MAX_APK = 100 * 1024 * 1024


class AppUploadForm(forms.Form):
    file = forms.FileField(label="File APK", widget=forms.ClearableFileInput(attrs={"accept": ".apk"}))
    notes = forms.CharField(label="Novità (facoltativo)", max_length=300, required=False)

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_APK:
            raise forms.ValidationError("File troppo grande.")
        try:
            info = read_apk(upload)
        except ApkError as exc:
            raise forms.ValidationError(str(exc)) from exc
        if info["package"] != settings.FASAS_SIGNER_ANDROID_PACKAGE:
            raise forms.ValidationError(f"Non è l'app FASAS Signer (pacchetto {info['package']}).")
        latest = SignerAppRelease.latest()
        if latest and info["versionCode"] <= latest.version_code:
            raise forms.ValidationError(f"La versione caricata ({info['versionName']}, n. {info['versionCode']}) non è "
                                        f"più recente di quella attuale (n. {latest.version_code}).")
        upload.seek(0)
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)
        self.apk_info, self.apk_sha256 = info, digest.hexdigest()
        return upload


@permission_required("signatures.manage_signer_devices", raise_exception=True)
def app_admin(request):
    form = AppUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        info = form.apk_info
        release = SignerAppRelease(
            version_code=info["versionCode"], version_name=info["versionName"] or str(info["versionCode"]),
            package=info["package"], debuggable=info["debuggable"], sha256=form.apk_sha256,
            size=form.cleaned_data["file"].size, notes=form.cleaned_data["notes"], uploaded_by=request.user)
        release.file.save(f"fasas-signer-{info['versionCode']}.apk", form.cleaned_data["file"], save=False)
        release.save()
        log_event(AuditLog.Action.CONFIG, release, user=request.user, changes={"app": [None, str(release)]})
        messages.success(request, f"App {release.version_name} pubblicata: il personale la trova in «App per il "
                                  "telefono» e chi ha la versione precedente riceve l'avviso nell'app.")
        if release.debuggable:
            messages.warning(request, "È una versione di prova: accetta anche FASAS in HTTP nella rete locale. Per "
                                      "l'uso con dati veri caricare la versione firmata con la chiave della struttura.")
        return redirect("signatures:app_admin")
    return render(request, "signatures/app_admin.html", {
        "form": form, "releases": SignerAppRelease.objects.select_related("uploaded_by")[:10],
        "package": settings.FASAS_SIGNER_ANDROID_PACKAGE,
    })


@login_required
def app_download(request):
    """Pagina per il personale: QR code da inquadrare col telefono, istruzioni, impronta del file."""
    import segno

    release = SignerAppRelease.latest()
    qr = None
    if release:
        url = request.build_absolute_uri(reverse("signatures:app_apk"))
        qr = segno.make(url, error="m").svg_inline(scale=5, border=2, dark="#0c1117", light="#ffffff")
    return render(request, "signatures/app_download.html", {"release": release, "qr": qr})


@never_cache
def app_apk(request):
    """Il file dell'app: senza accesso, così si scarica dal telefono inquadrando il QR (il codice dell'app è
    pubblico; chi la usa deve comunque essere abbinato da un utente del FASAS)."""
    release = SignerAppRelease.latest()
    if release is None:
        raise Http404("Nessuna app caricata.")
    response = FileResponse(release.file.open("rb"), content_type="application/vnd.android.package-archive",
                            as_attachment=True, filename=f"fasas-signer-{release.version_name}.apk")
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
def app_info(request):
    """Ultima versione dell'app per Android, per l'avviso di aggiornamento dentro l'app."""
    release = SignerAppRelease.latest()
    if release is None:
        return JsonResponse({"available": False})
    return JsonResponse({
        "available": True, "version_code": release.version_code, "version_name": release.version_name,
        "sha256": release.sha256, "size": release.size, "notes": release.notes,
        "url": request.build_absolute_uri(reverse("signatures:app_apk")),
        "page": request.build_absolute_uri(reverse("signatures:app_download")),
    })
