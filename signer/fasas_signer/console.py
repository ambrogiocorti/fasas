"""Interfaccia a riga di comando (computer senza finestre o per l'assistenza)."""
import getpass

from .engine import UserInterface


def is_access(request):
    """Verifica di identità per aprire un documento: la carta conferma chi sei, non firma il documento."""
    return request.get("purpose") == "access"


def describe(request):
    version = f" – versione {request['version']}" if request.get("version") else ""
    if is_access(request):
        return (f"Verifica di identità per aprire: {request['title']}\n"
                f"CODICE DI CONTROLLO: {request['verify_code']} (deve coincidere con quello mostrato dal FASAS)")
    return (f"Documento: {request['title']}{version}\n"
            f"Impronta SHA-256: {request['document_sha256'][:16]}…\n"
            f"CODICE DI CONTROLLO: {request['verify_code']} (deve coincidere con quello mostrato dal FASAS)")


class ConsoleUI(UserInterface):
    def confirm(self, request):
        if is_access(request):
            print("\nNuova verifica di identità con CIE\n" + describe(request))
            return input("Confermare l'identità con la CIE? [s/N] ").strip().lower() in ("s", "si", "sì", "y")
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
        if is_access(request):
            print("Identità verificata: torna al FASAS, il documento si apre.")
            return
        print(f"Documento firmato correttamente ({(result.get('verification') or {}).get('level', 'PAdES')}).")

    def failed(self, request, message):
        print(f"Firma non riuscita: {message}")
