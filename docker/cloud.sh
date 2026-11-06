#!/bin/bash
# Avvio della versione cloud (docs/CLOUD.md): un solo container con sito e pianificatore dei job.
# Se uno dei due si ferma, si ferma il container e il servizio di hosting lo riavvia.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p "${FASAS_MEDIA_ROOT:-/data/media}" "${FASAS_BACKUP_DIR:-/data/backups}"

# Schema del database aggiornato (le migrazioni già presenti non si ripetono), tabelle protette per Supabase
# (RLS attiva, nessun privilegio ai ruoli delle API) e configurazione iniziale: lo fa «migrate».
python manage.py migrate --noinput
python manage.py fasas_primo_amministratore

pids=()
if [ "${FASAS_SCHEDULER:-1}" = "1" ]; then
  python manage.py fasas_pianificatore &
  pids+=($!)
fi
# Memoria contenuta (istanze piccole): pochi processi, più thread; ogni processo si rinnova dopo 1000 richieste.
gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" --threads "${GUNICORN_THREADS:-4}" --timeout 120 \
  --max-requests 1000 --max-requests-jitter 100 --forwarded-allow-ips "*" --access-logfile - &
pids+=($!)

stop() { kill -TERM "${pids[@]}" 2>/dev/null || true; }
trap stop TERM INT
set +e
wait -n "${pids[@]}"
status=$?
stop
wait
exit "$status"
