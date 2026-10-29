from django.db import transaction

from fasas.audit.models import AuditLog
from fasas.audit.services import log_event
from fasas.core.encryption import delete_stored, store_encrypted
from fasas.documents.services import add_version, read_version

from .models import Signature, SigningCredential
from .providers import SignatureError, inspect_pkcs12, provider_for, signature_level


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


def register_remote(user, username, password, credential_id=""):
    """
    Collega l'utente alla sua firma remota: accede al prestatore con le sue credenziali (non salvate),
    individua la credenziale di firma e ne legge certificato e modalità di sblocco (PIN, OTP).
    """
    from . import csc

    config = csc.CSCConfig.from_settings()
    found, _ = csc.run(csc.discover(config, username, password, credential_id))
    if len(found) > 1 and not credential_id:
        ids = ", ".join(c.credential_id for c in found)
        raise SignatureError(f"Hai più credenziali di firma presso il prestatore ({ids}): indicare quale usare.")
    remote = found[0]
    credential, _ = SigningCredential.objects.get_or_create(user=user)
    old_storage = credential.storage_name
    credential.kind = SigningCredential.Kind.REMOTE
    credential.storage_name = ""
    credential.remote_user_id = username
    credential.remote_credential_id = remote.credential_id
    credential.remote_pin_required = remote.pin_required
    credential.remote_otp_type = remote.otp_type
    credential.certificate_subject = remote.subject
    credential.certificate_issuer = remote.issuer
    credential.certificate_serial = remote.serial
    credential.valid_from = remote.valid_from
    credential.valid_to = remote.valid_to
    credential.save()
    if old_storage:
        delete_stored(old_storage)
    log_event(AuditLog.Action.CONFIG, credential, user=user,
              changes={"firma remota": [None, f"{remote.subject} ({remote.credential_id})"]})
    return credential


def request_otp(user, password=""):
    """Chiede al prestatore l'invio dell'OTP via SMS. Restituisce il token di sessione da riusare per la firma."""
    from . import csc

    credential = getattr(user, "signing_credential", None)
    if credential is None or credential.kind != SigningCredential.Kind.REMOTE:
        raise SignatureError("Firma remota non configurata per il tuo utente.")
    config = csc.CSCConfig.from_settings()
    return csc.run(csc.request_otp(config, credential, credential.remote_user_id, password))


@transaction.atomic
def sign_version(version, user, secrets, reason="", location=""):
    """secrets: {"passphrase"} per il certificato PKCS#12, {"password", "pin", "otp", "token"} per la firma remota."""
    if isinstance(secrets, str):
        secrets = {"passphrase": secrets}
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
    level = signature_level()
    signed = provider_for(credential).sign_pdf(source, credential, secrets, reason, location)
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
        signature_format=f"PAdES-{level}",
        timestamped=level != "B-B",
    )
    log_event(AuditLog.Action.SIGN, signed_version, user=user, guest=version.document.guest,
              changes={"certificato": [None, signature.certificate_subject]}, reason=reason)
    return signature
