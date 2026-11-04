"""
Gruppo di continuità del server (scripts/gruppo_continuita.sh): NUT scrive l'ultimo evento in un file
(es. «ONBATT» quando manca la corrente) e questo job, ogni minuto, avvisa coordinatori e amministratori.
Così il turno sa che il server potrebbe spegnersi e prepara la modalità senza rete e il foglio di emergenza.
"""
import datetime
import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone

EVENTS = {
    "ONBATT": ("critical", "Corrente assente: server a batteria",
               "Il server del FASAS è alimentato dal gruppo di continuità. Se la corrente non torna si spegnerà da solo "
               "in modo ordinato: preparare i tablet per la modalità senza rete e il foglio di emergenza."),
    "LOWBATT": ("critical", "Batteria quasi scarica: il server si spegne",
                "Il FASAS si ferma in modo ordinato. Continuare in modalità senza rete o con il foglio di emergenza: "
                "al ritorno della corrente il server riparte da solo."),
    "FSD": ("critical", "Il server si sta spegnendo",
            "Batteria del gruppo di continuità quasi scarica: continuare in modalità senza rete o con il foglio di "
            "emergenza."),
    "ONLINE": ("info", "Corrente tornata", "Il server del FASAS è di nuovo alimentato dalla rete elettrica."),
    "COMMBAD": ("warning", "Gruppo di continuità non raggiungibile",
                "Il server non comunica con il gruppo di continuità: controllare il cavo USB."),
    "NOCOMM": ("warning", "Gruppo di continuità non raggiungibile",
               "Il server non comunica con il gruppo di continuità: controllare il cavo USB."),
    "COMMOK": ("info", "Gruppo di continuità di nuovo collegato", "La comunicazione con il gruppo è ripristinata."),
    "REPLBATT": ("warning", "Sostituire la batteria del gruppo di continuità",
                 "Il gruppo di continuità segnala che la batteria va sostituita."),
}


def is_configured():
    return bool(getattr(settings, "FASAS_UPS_STATUS_FILE", ""))


def read_status():
    """Ultimo evento scritto da NUT: {"evento": "ONBATT", "quando": datetime} oppure None."""
    try:
        data = json.loads(Path(settings.FASAS_UPS_STATUS_FILE).read_text(encoding="utf-8"))
        return {"evento": str(data["evento"]).upper(), "quando": datetime.datetime.fromisoformat(data["quando"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def check_events():
    """Job ogni minuto: avvisa per l'ultimo evento del gruppo (una volta sola per evento)."""
    if not is_configured():
        return {"enabled": False}
    from fasas.notifications.services import notify

    status = read_status()
    if status is None or status["evento"] not in EVENTS:
        return {"enabled": True, "evento": None}
    level, title, message = EVENTS[status["evento"]]
    sent = notify("power", title, message, level=level,
                  dedup_key=f"ups-{status['evento']}-{status['quando'].isoformat()}")
    return {"enabled": True, "evento": status["evento"], "avvisati": len(sent or [])}


def health():
    """(stato, descrizione) per /salute/, oppure None se il gruppo non è configurato."""
    if not is_configured():
        return None
    status = read_status()
    if status is None:
        return "warning", "stato del gruppo di continuità non disponibile"
    when = timezone.localtime(status["quando"]).strftime("%d/%m %H:%M")
    if status["evento"] in ("ONBATT", "LOWBATT", "FSD"):
        return "warning", f"a batteria dalle {when}"
    if status["evento"] in ("COMMBAD", "NOCOMM", "REPLBATT"):
        return "warning", f"{EVENTS[status['evento']][1].lower()} ({when})"
    return "ok", "alimentato dalla rete elettrica"
