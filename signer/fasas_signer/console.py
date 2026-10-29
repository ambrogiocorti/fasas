"""Interfaccia a riga di comando (computer senza finestre o per l'assistenza)."""
import getpass

from .engine import UserInterface


def describe(request):
    version = f" – versione {request['version']}" if request.get("version") else ""
    return (f"Documento: {request['title']}{version}\n"
            f"Impronta SHA-256: {request['document_sha256'][:16]}…\n"
            f"CODICE DI CONTROLLO: {request['verify_code']} (deve coincidere con quello mostrato dal FASAS)")


class ConsoleUI(UserInterface):
    def confirm(self, request):
        print("\nNuova richiesta di firma con CIE\n" + describe(request))
        return input("Firmare con la CIE? [s/N] ").strip().lower() in ("s", "si", "sì", "y")

    def ask_pin(self, request, message=None):
        if message:
            print(message)
        try:
            pin = getpass.getpass("PIN della CIE (ultime 4 cifre; invio vuoto per annullare): ")
        except (EOFError, KeyboardInterrupt):
            return None
        return pin or None

    def info(self, text):
        print(text)

    def done(self, request, result):
        print(f"Documento firmato correttamente ({(result.get('verification') or {}).get('level', 'PAdES')}).")

    def failed(self, request, message):
        print(f"Firma non riuscita: {message}")
