"""
FASAS Signer – uso:
  python -m fasas_signer                     finestra (uso normale)
  python -m fasas_signer abbina --server https://fasas.esempio.it/ --codice ABCD-EFGH [--nome "PC ambulatorio"]
  python -m fasas_signer console             firma da terminale (conferma e PIN digitati nel terminale)
  python -m fasas_signer diagnostica         Software CIE, lettori, carta e certificato (senza PIN)
Opzioni comuni: --libreria PERCORSO del modulo PKCS#11 (se non è nel percorso standard del Software CIE).
Senza lettore: --carta-di-prova FILE.p12 (creato da «manage.py fasas_carta_di_prova», NON è una CIE);
--usa-cie torna alla CIE.
"""
import argparse
import sys

from . import __version__, config
from .card import CardError, current_os, make_card
from .client import ServerClient, ServerError


def _settings(args, save=False):
    """Configurazione salvata, con le opzioni della riga di comando (ricordate se save=True)."""
    settings = config.load()
    changed = False
    if getattr(args, "libreria", None):
        settings["library"] = args.libreria
        changed = True
    if getattr(args, "carta_di_prova", None):
        from pathlib import Path

        settings["carta_di_prova"] = str(Path(args.carta_di_prova).resolve())
        changed = True
    if getattr(args, "usa_cie", False) and settings.pop("carta_di_prova", None):
        changed = True
    if save and changed:
        config.save(settings)
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
    card = make_card(_settings(args, save=True))
    info = card.status()
    print(f"FASAS Signer {__version__} su {info['os']}")
    if getattr(card, "is_test", False):
        print(f"CARTA DI PROVA (non è una CIE, nessun valore legale): {info.get('middleware_path')}")
    else:
        print(f"Modulo PKCS#11: {info.get('middleware_path') or 'NON TROVATO'} {info.get('middleware', '')}")
    print(f"Lettori: {', '.join(info.get('readers', [])) or 'nessuno'}")
    print(f"Carta sul lettore: {'sì' if info.get('card_present') else 'no'}")
    if info.get("card_present"):
        try:
            describe_certificate(card.certificate())
        except CardError as exc:
            print(f"Certificato: {exc}")
        except ImportError:
            print("Certificato: letto (installare «cryptography» per vederne i dati).")


CF_RE = r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]"


def describe_certificate(der):
    """Dati pubblici del certificato: servono a capire perché il FASAS lo accetta o lo rifiuta (nessun PIN)."""
    import re

    from cryptography import x509
    from cryptography.x509.oid import AuthorityInformationAccessOID, NameOID

    if der[:1] == b"\x30" and der[1] & 0x80:  # il file sul chip può avere zeri di riempimento in coda
        count = der[1] & 0x7F
        der = der[:2 + count + int.from_bytes(der[2:2 + count], "big")]
    cert = x509.load_der_x509_certificate(der)
    print(f"Titolare: {cert.subject.rfc4514_string()}")
    print(f"Emittente: {cert.issuer.rfc4514_string()}")
    print(f"Validità: {cert.not_valid_before_utc:%d/%m/%Y} – {cert.not_valid_after_utc:%d/%m/%Y}")
    values = [a.value for oid in (NameOID.COMMON_NAME, NameOID.SERIAL_NUMBER)
              for a in cert.subject.get_attributes_for_oid(oid)]
    codes = sorted({c for v in values for c in re.findall(CF_RE, str(v).upper())})
    print(f"Codice fiscale letto: {', '.join(codes) or 'NON TROVATO (il FASAS rifiuterà la firma)'}")
    try:
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        print(f"Uso della chiave: firma digitale {'sì' if usage.digital_signature else 'no'}, "
              f"non ripudio {'sì' if usage.content_commitment else 'no'}")
    except x509.ExtensionNotFound:
        print("Uso della chiave: non indicato (il FASAS rifiuterà la firma)")
    try:
        aia = cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
        for item in aia:
            kind = "certificato dell'emittente" if item.access_method == AuthorityInformationAccessOID.CA_ISSUERS else "OCSP"
            print(f"{kind}: {item.access_location.value}")
    except x509.ExtensionNotFound:
        pass


def cmd_console(args):
    from .console import ConsoleUI
    from .engine import Service

    settings = _settings(args, save=True)
    if not settings.get("token"):
        sys.exit("Dispositivo non abbinato: eseguire prima «abbina».")
    client = ServerClient(settings["server"], settings["token"], allow_http=settings.get("allow_http", False))
    card = make_card(settings)
    if getattr(card, "is_test", False):
        print("ATTENZIONE: CARTA DI PROVA – non è una CIE, le firme non hanno valore legale.")
    print(f"In linea come {client.me()['user']}. In attesa di richieste di firma (Ctrl+C per uscire)…")
    try:
        Service(client, card, ConsoleUI()).run()
    except KeyboardInterrupt:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fasas_signer", description="FASAS Signer – firma con CIE")
    parser.add_argument("--libreria", help="percorso del modulo PKCS#11 del Software CIE")
    parser.add_argument("--carta-di-prova", help="file .p12 della carta di prova (solo prove senza lettore, NON è una CIE)")
    parser.add_argument("--usa-cie", action="store_true", help="smette di usare la carta di prova")
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
            _settings(args, save=True)
            from .gui import main as gui_main

            gui_main()
    except (ServerError, ValueError, CardError) as exc:
        sys.exit(f"Errore: {exc}")


if __name__ == "__main__":
    main()
