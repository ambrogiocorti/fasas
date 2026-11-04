"""
Mostra i certificati della CSCA italiana caricati dal FASAS (FASAS_CIE_CSCA, oppure la cartella «certificati-csca»),
con l'impronta SHA-1 scritta come sul sito del Ministero (https://csca-ita.interno.gov.it): si confrontano a occhio
prima di attivare la «CIE + PIN FASAS».

    python manage.py fasas_csca
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from fasas.signatures.nis import NisError, csca_files


class Command(BaseCommand):
    help = "Elenca i certificati CSCA caricati, con impronta SHA-1 da confrontare con il sito del Ministero."

    def handle(self, *args, **options):
        from cryptography.hazmat.primitives import hashes

        if not settings.FASAS_CIE_CSCA:
            raise CommandError("Nessun certificato CSCA: creare la cartella «certificati-csca» nella cartella del FASAS "
                               "con i file .cer scaricati da https://csca-ita.interno.gov.it (o impostare FASAS_CIE_CSCA).")
        try:
            files = csca_files()
        except NisError as exc:
            raise CommandError(str(exc)) from exc
        if not files:
            raise CommandError(f"Nessun certificato trovato in {settings.FASAS_CIE_CSCA}.")
        now = timezone.now()
        self.stdout.write(f"Certificati in {settings.FASAS_CIE_CSCA}:\n")
        for name, cert in files:
            # SHA-1 solo per confrontare a occhio l'impronta con quella pubblicata dal Ministero
            digest = cert.fingerprint(hashes.SHA1())  # nosec B303
            sha1 = " ".join(f"{b:02x}" for b in digest)
            valid = cert.not_valid_before_utc <= now <= cert.not_valid_after_utc
            self.stdout.write(f"{name}\n  {cert.subject.rfc4514_string()}\n  SHA-1: {sha1}\n"
                              f"  valido dal {cert.not_valid_before_utc:%d/%m/%Y} al {cert.not_valid_after_utc:%d/%m/%Y}"
                              f"{'' if valid else '  (SCADUTO)'}\n")
        self.stdout.write(self.style.SUCCESS(f"{len(files)} certificati caricati. Confronta le impronte SHA-1 con quelle "
                                             "del sito https://csca-ita.interno.gov.it."))
