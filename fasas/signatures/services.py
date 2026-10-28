from django.conf import settings
from django.db import transaction

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import delete_stored, store_encrypted
from fasas.documents.services import add_version, read_version

from .models import Signature, SigningCredential
from .providers import SignatureError, inspect_pkcs12, provider_for


def register_pkcs12(user, p12_bytes, passphrase):
    """Verifica il certificato con la passphrase (che non viene salvata) e lo archivia cifrato."""
    info = inspect_pkcs12(p12_bytes, passphrase)
    credential, _ = SigningCredential.objects.get_or_create(user=user)
    old_storage = credential.storage_name
    credential.kind = SigningCredential.Kind.PKCS12
    credential.storage_name = store_encrypted(p12_bytes, "signing")
    credential.certificate_subject = info.subject[:255]
    credential.certificate_issuer = info.issuer[:255]
    credential.certificate_serial = info.serial
    credential.valid_from = info.valid_from
    credential.valid_to = info.valid_to
    credential.save()
    if old_storage:
        delete_stored(old_storage)
    log_event(AuditLog.Action.CONFIG, credential, user=user, changes={"certificato": [None, info.subject]})
    return credential


@transaction.atomic
def sign_version(version, user, secret, reason="", location=""):
    if not user.has_perm("signatures.sign_document"):
        raise SignatureError("Non hai il permesso di firmare documenti.")
    if not version.is_pdf:
        raise SignatureError("Si possono firmare in formato PAdES solo documenti PDF.")
    credential = getattr(user, "signing_credential", None)
    if credential is None:
        raise SignatureError("Nessuna credenziale di firma configurata per il tuo utente.")
    if not credential.is_valid_now:
        raise SignatureError("Il certificato di firma è scaduto o non ancora valido.")

    source = read_version(version, user=user, audit=False)
    location = location or str(version.document.guest.community)
    signed = provider_for(credential).sign_pdf(source, credential, secret, reason, location)
    signed_version = add_version(
        version.document, signed, version.original_name.rsplit(".", 1)[0] + "_firmato.pdf", user,
        note=f"Firmato digitalmente da {user}", content_type="application/pdf", is_signed=True,
    )
    signature = Signature.objects.create(
        source_version=version,
        signed_version=signed_version,
        signer=user,
        provider=credential.kind,
        certificate_subject=credential.certificate_subject or str(user),
        certificate_issuer=credential.certificate_issuer,
        certificate_serial=credential.certificate_serial,
        reason=reason,
        timestamped=bool(settings.FASAS_SIGNATURE_TSA_URL),
    )
    log_event(AuditLog.Action.SIGN, signed_version, user=user, guest=version.document.guest,
              changes={"certificato": [None, signature.certificate_subject]}, reason=reason)
    return signature
