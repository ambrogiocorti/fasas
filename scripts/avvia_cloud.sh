#!/usr/bin/env bash
# Versione cloud su un hosting Python senza Docker (server persistente, porta in PORT o SERVER_PORT).
# Stesso avvio del container (docker/cloud.sh): migrazioni, primo amministratore, pianificatore e sito.
# Non installa pacchetti né genera chiavi: dipendenze con «pip install --require-hashes -r requirements.lock»,
# variabili (.env.cloud.example) nel pannello del fornitore. Guida: docs/CLOUD.md.
set -euo pipefail
cd "$(dirname "$0")/.."

export FASAS_CLOUD=1 DJANGO_DEBUG=0
export FASAS_MEDIA_ROOT="${FASAS_MEDIA_ROOT:-$PWD/runtime/media}"
export FASAS_BACKUP_DIR="${FASAS_BACKUP_DIR:-$PWD/runtime/backups}"
export GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}" GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
if [[ -z "${PORT:-}" && "${SERVER_PORT:-}" =~ ^[0-9]+$ ]]; then export PORT="$SERVER_PORT"; fi
[[ "${PORT:-}" =~ ^[0-9]+$ ]] || { echo "Impostare PORT (o SERVER_PORT) con la porta assegnata dal fornitore." >&2; exit 1; }

if ! command -v pg_dump > /dev/null 2>&1; then
  echo "ATTENZIONE: pg_dump non c'è: i backup non sarebbero ripristinabili su PostgreSQL. Niente dati reali finché manca." >&2
fi
python manage.py collectstatic --noinput --verbosity 0
exec bash docker/cloud.sh
