import getpass
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from fasas.core import keys
from fasas.core.models import Community


class Command(BaseCommand):
    help = ("Custodia delle chiavi: «verifica» (le chiavi configurate aprono i dati?), «busta FILE» (busta cifrata "
            "da conservare fuori dal server), «apri FILE» (righe .env per ripristinare le chiavi)")

    def add_arguments(self, parser):
        parser.add_argument("azione", choices=["verifica", "busta", "apri"])
        parser.add_argument("file", nargs="?", help="Percorso della busta di custodia")
        parser.add_argument("--frase-da-file", help="Legge la frase segreta da un file invece di chiederla")

    def _passphrase(self, options, confirm):
        if options["frase_da_file"]:
            return Path(options["frase_da_file"]).read_text(encoding="utf-8").strip()
        first = getpass.getpass("Frase segreta della busta (almeno 12 caratteri): ")
        if confirm and getpass.getpass("Ripeti la frase segreta: ") != first:
            raise CommandError("Le due frasi non coincidono.")
        return first

    def handle(self, *args, **options):
        action = options["azione"]
        if action == "verifica":
            failed = False
            for kind, state, detail in keys.check_keys():
                failed |= state != "ok"
                self.stdout.write(f"{kind:10} {'OK ' if state == 'ok' else 'ERRORE'} {detail}")
            for label, value in keys.fingerprints().items():
                self.stdout.write(f"impronta {label}: {value}")
            if failed:
                raise CommandError("Chiavi non corrette: NON usare il sistema finché non si ripristina la chiave giusta.")
            return
        if not options["file"]:
            raise CommandError("Indicare il percorso della busta.")
        path = Path(options["file"])
        if action == "busta":
            if path.exists():
                raise CommandError(f"{path} esiste già: scegliere un altro nome.")
            try:
                data = keys.make_envelope(self._passphrase(options, confirm=True), str(Community.default()))
            except keys.EnvelopeError as exc:
                raise CommandError(str(exc)) from exc
            path.write_bytes(data)
            path.chmod(0o600)
            self.stdout.write(self.style.SUCCESS(f"Busta di custodia creata: {path}"))
            self.stdout.write("Foglio di custodia (da stampare e firmare; NON contiene le chiavi):")
            for label, value in keys.fingerprints().items():
                self.stdout.write(f"  impronta {label}: {value}")
            self.stdout.write("  Conservare la busta in due luoghi (es. chiavetta in cassaforte e gestore di password "
                              "della direzione) e la frase segreta separata dalla busta.")
            return
        try:
            envelope = keys.open_envelope(path.read_bytes(), self._passphrase(options, confirm=False))
        except keys.EnvelopeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"# Busta del {envelope['created_at']} – {envelope.get('community', '')}")
        for line in keys.env_lines(envelope):
            self.stdout.write(line)
