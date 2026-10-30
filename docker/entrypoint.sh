#!/bin/sh
# Avvio dei container FASAS: «web» (sito), «worker» (job periodici), oppure un comando qualsiasi.
set -e
case "$1" in
  web)
    python manage.py migrate --noinput
    # i file statici dell'immagine vanno nel volume condiviso con il proxy HTTPS
    if [ -d /static ] && [ -w /static ]; then cp -r /app/staticfiles/. /static/; fi
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" \
      --timeout 120 --forwarded-allow-ips "*" --access-logfile -
    ;;
  worker)
    # job periodici (turni, protocolli, backup, verifica audit…) con lo scheduler integrato
    exec celery -A config worker -B --loglevel INFO --schedule /data/celerybeat-schedule --concurrency 2
    ;;
  *)
    exec "$@"
    ;;
esac
