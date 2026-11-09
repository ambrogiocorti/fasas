#!/usr/bin/env bash
# Presentazione online del FASAS su PythonAnywhere (account gratuito, senza carta): docs/PRESENTAZIONE.md.
# Si lancia nella console «Bash» di PythonAnywhere, dalla cartella del FASAS:
#
#   ./scripts/presentazione_pythonanywhere.sh              installazione (e aggiornamento dopo «git pull»)
#   ./scripts/presentazione_pythonanywhere.sh --rigenera   dati di esempio di nuovo come all'inizio, con le date di oggi
#
# Dati inventati e chiavi di cifratura pubbliche di prova: MAI dati di persone reali.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
RESET=""
[ "${1:-}" = "--rigenera" ] && RESET=1

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
die() { printf '\n\033[31mERRORE:\033[0m %s\n' "$*" >&2; exit 1; }

USER_NAME=$(whoami)
# «eu.pythonanywhere.com» per gli account europei; se la console non lo dice, lo si ricava dal sito già creato
DOMAIN="${PYTHONANYWHERE_DOMAIN:-}"
if [ -z "$DOMAIN" ]; then
  if [ -f "/var/www/${USER_NAME}_eu_pythonanywhere_com_wsgi.py" ]; then DOMAIN=eu.pythonanywhere.com
  else DOMAIN=pythonanywhere.com; fi
fi
HOST="$USER_NAME.$DOMAIN"
DATA="$HOME/fasas-presentazione"
VENV="$HOME/.virtualenvs/fasas"
WSGI="/var/www/$(printf '%s' "$HOST" | tr '.-' '__')_wsgi.py"

say "FASAS Digitale – presentazione su https://$HOST"

# --- 1. Python e librerie (circa 200 MB, la prima volta qualche minuto) ---------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  PY=""
  for version in 3.13 3.12 3.11 3.10; do
    command -v "python$version" > /dev/null && { PY="python$version"; break; }
  done
  [ -n "$PY" ] || die "nessun Python 3.10–3.13 disponibile in questa console."
  "$PY" -m venv "$VENV"
fi
PY_VERSION=$("$VENV/bin/python" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
"$VENV/bin/pip" install --quiet --disable-pip-version-check --no-cache-dir --require-hashes -r requirements.lock
ok "librerie installate (Python $PY_VERSION, ambiente $VENV)"

# --- 2. Configurazione della presentazione (una volta: la chiave segreta non cambia) ---------------------------
mkdir -p "$DATA"
if [ ! -f .env ]; then
  SECRET=$("$VENV/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')
  cat > .env <<ENV
# Presentazione del FASAS su PythonAnywhere – creato da scripts/presentazione_pythonanywhere.sh
FASAS_PRESENTAZIONE=1
DJANGO_SECRET_KEY=$SECRET
FASAS_DOMAIN=$HOST,$USER_NAME.eu.pythonanywhere.com,$USER_NAME.pythonanywhere.com
FASAS_PRESENTAZIONE_DB=$DATA/presentazione.sqlite3
FASAS_MEDIA_ROOT=$DATA/file
FASAS_BACKUP_DIR=$DATA/backup
# l'HTTPS lo gestisce PythonAnywhere («Force HTTPS» nella scheda Web)
DJANGO_SECURE_SSL_REDIRECT=0
FASAS_LOG_LEVEL=WARNING
ENV
  chmod 600 .env
  ok "configurazione creata (.env)"
else
  grep -q '^FASAS_PRESENTAZIONE=1$' .env || die "c'è già un .env che non è di una presentazione: non lo tocco."
  ok "configurazione già presente (.env)"
fi

# --- 3. Database con i dati di esempio --------------------------------------------------------------------------
if [ -n "$RESET" ] || [ ! -f "$DATA/presentazione.sqlite3" ]; then
  rm -rf "$DATA/presentazione.sqlite3" "$DATA/file" "$DATA/backup"
  "$VENV/bin/python" manage.py migrate --noinput --verbosity 0
  "$VENV/bin/python" manage.py fasas_demo --ambiente-di-prova | tail -n 1
  ok "dati di esempio creati con le date di oggi"
else
  "$VENV/bin/python" manage.py migrate --noinput --verbosity 0
  ok "database aggiornato (dati di prima conservati; per ricominciare: --rigenera)"
fi
"$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0
ok "file statici pronti"

# --- 4. Collegamento al sito (file WSGI della scheda Web) -------------------------------------------------------
if [ -f "$WSGI" ]; then
  cat > "$WSGI" <<PYWSGI
# FASAS Digitale – presentazione (scritto da scripts/presentazione_pythonanywhere.sh)
import os
import sys

if "$ROOT" not in sys.path:
    sys.path.insert(0, "$ROOT")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
PYWSGI
  touch "$WSGI"
  ok "sito collegato e riavviato ($WSGI)"
  say "Fatto. Nella scheda Web controllare una volta sola:"
  echo "  - Python version: $PY_VERSION"
  echo "  - Virtualenv: $VENV"
  echo "  - Force HTTPS: Enabled"
  echo "  poi premere il pulsante verde «Reload» e aprire https://$HOST"
else
  say "Manca ancora il sito nella scheda Web. Fare così e poi rilanciare questo script:"
  echo "  Web › Add a new web app › Next › Manual configuration › Python $PY_VERSION › Next"
fi
echo
echo "Utenti: admin, coordinatore, operatore, medico, amministrativo – password nella pagina di accesso."
