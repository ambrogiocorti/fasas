#!/bin/sh
# Avvio dei container FASAS: «web» (sito), «worker» (job periodici), «cloud» (sito e job insieme, versione cloud),
# oppure un comando qualsiasi.
set -e
mkdir -p "${FASAS_MEDIA_ROOT:-/data/media}" "${FASAS_BACKUP_DIR:-/data/backups}"
case "$1" in
  web)
    # con FASAS_PRESENTAZIONE=1 o FASAS_CLOUD=1 lo stesso comando avvia la versione di presentazione o cloud:
    # nessun comando da impostare sul servizio di hosting
    if [ "${FASAS_PRESENTAZIONE:-0}" = "1" ]; then exec /app/docker/presentazione.sh; fi
    if [ "${FASAS_CLOUD:-0}" = "1" ]; then exec /app/docker/cloud.sh; fi
    python manage.py migrate --noinput
    # i file statici dell'immagine vanno nel volume condiviso con il proxy HTTPS
    if [ -d /static ] && [ -w /static ]; then cp -r /app/staticfiles/. /static/; fi
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" \
      --timeout 120 --forwarded-allow-ips "*" --access-logfile -
    ;;
  cloud)
    # versione cloud: sito + pianificatore integrato nello stesso container, porta $PORT (docs/CLOUD.md)
    exec /app/docker/cloud.sh
    ;;
  worker)
    # job periodici (turni, protocolli, backup, verifica audit…) con lo scheduler integrato
    exec celery -A config worker -B --loglevel INFO --schedule /data/celerybeat-schedule --concurrency 2
    ;;
  *)
    exec "$@"
    ;;
esac
