"""Variabili dei moduli ({titolare}, {ospite}…): nessuna dipendenza dal database, la usa anche lo script del pacchetto."""
import re

VARIABLE = re.compile(r"\{(titolare|sede|contatti|dpo|contatti_dpo|struttura|ospite|utente|ruolo)\}")
FALLBACK = {"ospite": "l'ospite", "utente": "______________________________", "ruolo": "____________________"}
# sui moduli stampati senza intestazione configurata
PAPER = {"titolare": "[titolare del trattamento]", "sede": "[sede]", "contatti": "[recapiti del titolare]",
         "dpo": "[responsabile della protezione dei dati]", "contatti_dpo": "[recapiti del DPO]",
         "struttura": "[struttura]"}


def substitute(text, values, fallback=None):
    fallback = {**FALLBACK, **(fallback or {})}
    return VARIABLE.sub(lambda m: values.get(m.group(1)) or fallback.get(m.group(1)) or f"[{m.group(1)}]",
                        text or "")


def default_snapshot(data, version=1):
    """Fotografia di un modulo predefinito (fasas.modulistica.defaults) per la stampa senza database."""
    fields = [{"key": key, "label": label, "kind": kind, "required": required, "options": list(options),
               "help_text": help_text} for key, label, kind, required, options, help_text in data.get("fields", [])]
    return {"code": data["code"], "title": data["title"], "version": version,
            "intro": substitute(data.get("intro", ""), {}, PAPER), "requires_signature": data.get("requires_signature", False),
            "signatures": data.get("signatures") or [], "fields": fields,
            "header": {"holder": PAPER["titolare"], "address": PAPER["sede"]},
            "subject_label": "Ospite" if data.get("for_guests") else "Dipendente" if data.get("for_staff") else ""}
