from django.apps import AppConfig


class SignaturesConfig(AppConfig):
    name = "fasas.signatures"
    verbose_name = "Firma digitale"

    def ready(self):
        from fasas.audit.services import register

        from .models import SignatureRequest, SignerDevice, SigningCredential

        register(SigningCredential, exclude={"storage_name"}, guest_field=None)
        # Ogni passaggio di stato della firma con CIE resta nell'audit; esclusi PDF preparati, nonce e certificato
        register(SignatureRequest, exclude={"prepared", "prepared_storage", "result_storage", "nonce_hash", "certificate",
                                            "verification"}, guest_field="version__document__guest")
        register(SignerDevice, exclude={"token_hash", "status", "status_at", "last_seen_at"}, guest_field=None)
        _load_pyhanko_cms_names()


def _load_pyhanko_cms_names():
    """
    pyHanko aggiunge nomi di attributi CMS ad asn1crypto (es. signing_certificate_v2) senza aggiornarne la tabella
    inversa, che asn1crypto costruisce una sola volta al primo uso. Se qualcosa usa quei nomi prima di pyHanko (per
    esempio la verifica della CIE senza PIN), la firma PAdES fallirebbe: si carica pyHanko subito e si azzera la tabella.
    """
    try:
        import pyhanko.sign.ades.cades_asn1  # noqa: F401
        from asn1crypto import cms
    except ImportError:  # pragma: no cover - pyHanko è una dipendenza obbligatoria
        return
    cms.CMSAttributeType._reverse_map = None
