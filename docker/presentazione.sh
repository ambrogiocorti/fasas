#!/bin/bash
# Versione di presentazione (docs/PRESENTAZIONE.md): il FASAS online con dati inventati, senza nulla da configurare.
# A ogni avvio il database di prova si ricrea con le date di oggi; poi parte come la versione cloud (sito + job).
set -euo pipefail
cd "$(dirname "$0")/.."
export FASAS_PRESENTAZIONE=1
export FASAS_PRESENTAZIONE_DB="${FASAS_PRESENTAZIONE_DB:-/data/presentazione.sqlite3}"
HERE=$(dirname "$FASAS_PRESENTAZIONE_DB")
# cartelle solo della presentazione: si svuotano a ogni avvio insieme al database
export FASAS_MEDIA_ROOT="$HERE/presentazione-file" FASAS_BACKUP_DIR="$HERE/presentazione-backup"
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
  export DJANGO_SECRET_KEY
fi
mkdir -p "$HERE"
rm -rf "$FASAS_PRESENTAZIONE_DB" "$FASAS_PRESENTAZIONE_DB-journal" "$FASAS_MEDIA_ROOT" "$FASAS_BACKUP_DIR"
mkdir -p "$FASAS_MEDIA_ROOT" "$FASAS_BACKUP_DIR"
# schema già preparato nell'immagine (Dockerfile): all'avvio restano da creare solo i dati di esempio
[ -f presentazione/base.sqlite3 ] && cp presentazione/base.sqlite3 "$FASAS_PRESENTAZIONE_DB"
python manage.py migrate --noinput --verbosity 0
python manage.py fasas_demo --ambiente-di-prova
exec bash docker/cloud.sh
