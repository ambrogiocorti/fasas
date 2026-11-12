"""
Avvia il FASAS di prova raggiungibile dagli altri dispositivi della stessa rete (es. il telefono con FASAS Signer).

Solo per prove (DJANGO_DEBUG=1): ascolta su tutte le interfacce, ammette come indirizzo del sito gli IP della rete
locale del computer e li mostra, così da inserirli nell'app. In produzione il FASAS va pubblicato in HTTPS.
"""
import ipaddress
import os
import socket

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

LAN_NETWORKS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]  # RFC 1918


def lan_addresses():
    """Indirizzi IPv4 privati del computer (Wi-Fi o cavo), il principale per primo."""
    found = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 80))  # indirizzo di documentazione: con UDP non parte alcun pacchetto
        found.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    result = []
    for ip in found:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if address.version == 4 and any(address in net for net in LAN_NETWORKS) and ip not in result:
            result.append(ip)
    return result


class Command(BaseCommand):
    help = "Avvia il FASAS di prova raggiungibile dal telefono sulla stessa rete Wi-Fi (solo con DJANGO_DEBUG=1)."

    def add_arguments(self, parser):
        parser.add_argument("--porta", type=int, default=8000)

    def handle(self, porta, **options):
        if not settings.DEBUG:
            raise CommandError("Solo per le prove (DJANGO_DEBUG=1): in produzione il FASAS va pubblicato in HTTPS.")
        addresses = lan_addresses()
        if not addresses:
            raise CommandError("Il computer non sembra collegato a una rete locale (Wi-Fi o cavo).")
        hosts = ["localhost", "127.0.0.1", *addresses]
        # Variabile d'ambiente per il processo del server (riavviato a ogni modifica) e impostazione per questo
        os.environ["DJANGO_ALLOWED_HOSTS"] = ",".join(hosts)
        settings.ALLOWED_HOSTS = hosts
        self.stdout.write(self.style.SUCCESS("FASAS di prova raggiungibile dalla rete locale."))
        self.stdout.write("Indirizzo da inserire nell'app FASAS Signer sul telefono (stessa rete Wi-Fi):")
        for address in addresses:
            self.stdout.write(self.style.SUCCESS(f"   http://{address}:{porta}/"))
        self.stdout.write("Sul computer il FASAS resta su http://127.0.0.1:%d/ . Se Windows chiede di consentire "
                          "l'accesso a Python, consentilo per le reti private." % porta)
        call_command("runserver", f"0.0.0.0:{porta}")
