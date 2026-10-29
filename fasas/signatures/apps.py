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
