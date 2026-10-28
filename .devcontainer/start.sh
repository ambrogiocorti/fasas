#!/usr/bin/env bash
# A ogni apertura del Codespace: scarica le ultime modifiche e avvia il sistema.
set -uo pipefail
if git diff --quiet && git diff --cached --quiet; then
  git pull --ff-only --quiet || echo "Aggiornamento non riuscito: si avvia la versione già presente."
else
  echo "Ci sono modifiche locali: aggiornamento automatico saltato."
fi
pip install --quiet --disable-pip-version-check -r requirements.txt
python manage.py migrate --verbosity 0
python manage.py fasas_demo --skip-if-exists
echo
echo "FASAS Digitale è avviato: si apre nella scheda «Porte» (porta 8000)."
echo "Utenti: admin, coordinatore, operatore, medico – password: Demo-Fasas-2026!"
echo
exec python manage.py runserver 0.0.0.0:8000
