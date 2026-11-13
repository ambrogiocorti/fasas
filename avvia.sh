#!/usr/bin/env bash
# FASAS Digitale - avvio di prova su Mac e Linux:  ./avvia.sh
# Se la cartella è stata scaricata con git, prima scarica gli aggiornamenti.
set -uo pipefail
cd "$(dirname "$0")"
echo "=== FASAS Digitale - avvio di prova ==="
if command -v git >/dev/null && [ -d .git ]; then
  echo "Scarico gli aggiornamenti..."
  git pull --ff-only || echo "Aggiornamento non riuscito: si avvia la versione già presente."
else
  echo "[!] Cartella non collegata a git: gli aggiornamenti non vengono scaricati in automatico."
fi
if [ ! -x .venv/bin/python ]; then
  echo "Creo l'ambiente Python, solo la prima volta..."
  python3 -m venv .venv || { echo "[!] Python 3 non trovato: installalo da https://www.python.org/downloads/"; exit 1; }
fi
source .venv/bin/activate
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
[ -f .env ] || echo "DJANGO_DEBUG=1" > .env
python manage.py migrate --verbosity 0
# chiavi pubbliche e password note: si ferma se trova ospiti veri
python manage.py fasas_controllo_prova || { echo "[!] Avvio di prova fermato."; exit 1; }
python manage.py fasas_demo --skip-if-exists
echo
echo "Apri http://127.0.0.1:8000"
echo "Utenti: gestore, coordinatore, operatore, medico, ufficio, familiare - password: Demo-Fasas-2026!"
echo "Per fermare il sistema premi CTRL+C."
echo
( sleep 4; command -v open >/dev/null && open http://127.0.0.1:8000 || xdg-open http://127.0.0.1:8000 ) >/dev/null 2>&1 &
# «./avvia.sh telefono»: raggiungibile dal telefono (app FASAS Signer) sulla stessa rete Wi-Fi
[ "${1:-}" = "telefono" ] && exec python manage.py fasas_avvia_rete
exec python manage.py runserver
