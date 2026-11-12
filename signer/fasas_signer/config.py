"""Configurazione locale: indirizzo del FASAS, token del dispositivo e percorso del modulo PKCS#11."""
import json
import os
import sys
from pathlib import Path


def config_dir():
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return Path(os.environ.get("FASAS_SIGNER_HOME", base / "FASAS Signer"))


def config_path():
    return config_dir() / "config.json"


def load():
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data):
    """Il file contiene il token del dispositivo: leggibile solo dall'utente (0600 su macOS/Linux)."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)
    return path
