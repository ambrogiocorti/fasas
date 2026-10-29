"""
FASAS Signer – uso:
  python -m fasas_signer                     finestra (uso normale)
  python -m fasas_signer abbina --server https://fasas.esempio.it/ --codice ABCD-EFGH [--nome "PC ambulatorio"]
  python -m fasas_signer console             firma da terminale (conferma e PIN digitati nel terminale)
  python -m fasas_signer diagnostica         Software CIE, lettori, carta e certificato (senza PIN)
Opzioni comuni: --libreria PERCORSO del modulo PKCS#11 (se non è nel percorso standard del Software CIE).
"""
import argparse
import sys

from . import __version__, config
from .card import CardError, Pkcs11Card, current_os
from .client import ServerClient, ServerError


def _settings(args):
    settings = config.load()
    if getattr(args, "libreria", None):
        settings["library"] = args.libreria
    return settings


def cmd_pair(args):
    settings = _settings(args)
    client = ServerClient(args.server, allow_http=args.http)
    data = client.pair(args.codice, args.nome, {"windows": "windows", "macos": "macos", "linux": "linux"}.get(
        current_os(), "other"))
    settings.update({"server": args.server, "token": data["token"], "name": args.nome, "allow_http": args.http})
    path = config.save(settings)
    print(f"Abbinato all'utente {data['user']}. Configurazione salvata in {path}.")
    if not data.get("fiscal_code_configured"):
        print("Attenzione: nel profilo FASAS manca il codice fiscale, necessario per firmare.")


def cmd_diagnose(args):
    card = Pkcs11Card(_settings(args).get("library", ""))
    info = card.status()
    print(f"FASAS Signer {__version__} su {info['os']}")
    print(f"Modulo PKCS#11: {info.get('middleware_path') or 'NON TROVATO'} {info.get('middleware', '')}")
    print(f"Lettori: {', '.join(info.get('readers', [])) or 'nessuno'}")
    print(f"Carta sul lettore: {'sì' if info.get('card_present') else 'no'}")
    if info.get("card_present"):
        try:
            from cryptography import x509

            cert = x509.load_der_x509_certificate(card.certificate())
            print(f"Certificato: {cert.subject.rfc4514_string()} – valido fino al {cert.not_valid_after_utc:%d/%m/%Y}")
        except CardError as exc:
            print(f"Certificato: {exc}")
        except ImportError:
            print("Certificato: letto (installare «cryptography» per vederne i dati).")


def cmd_console(args):
    from .console import ConsoleUI
    from .engine import Service

    settings = _settings(args)
    if not settings.get("token"):
        sys.exit("Dispositivo non abbinato: eseguire prima «abbina».")
    client = ServerClient(settings["server"], settings["token"], allow_http=settings.get("allow_http", False))
    print(f"In linea come {client.me()['user']}. In attesa di richieste di firma (Ctrl+C per uscire)…")
    try:
        Service(client, Pkcs11Card(settings.get("library", "")), ConsoleUI()).run()
    except KeyboardInterrupt:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fasas_signer", description="FASAS Signer – firma con CIE")
    parser.add_argument("--libreria", help="percorso del modulo PKCS#11 del Software CIE")
    sub = parser.add_subparsers(dest="command")
    pair = sub.add_parser("abbina", help="abbina questo computer al proprio utente FASAS")
    pair.add_argument("--server", required=True)
    pair.add_argument("--codice", required=True)
    pair.add_argument("--nome", default="PC con lettore CIE")
    pair.add_argument("--http", action="store_true", help="solo sviluppo: consente HTTP verso un server non locale")
    sub.add_parser("console", help="firma da terminale")
    sub.add_parser("diagnostica", help="controlla Software CIE, lettore e carta")
    args = parser.parse_args(argv)
    try:
        if args.command == "abbina":
            cmd_pair(args)
        elif args.command == "diagnostica":
            cmd_diagnose(args)
        elif args.command == "console":
            cmd_console(args)
        else:
            if args.libreria:
                settings = config.load()
                settings["library"] = args.libreria
                config.save(settings)
            from .gui import main as gui_main

            gui_main()
    except (ServerError, ValueError, CardError) as exc:
        sys.exit(f"Errore: {exc}")


if __name__ == "__main__":
    main()
