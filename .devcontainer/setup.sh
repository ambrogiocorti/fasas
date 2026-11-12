#!/usr/bin/env bash
# Prima creazione del Codespace: librerie, configurazione di prova, database e dati demo.
set -euo pipefail
pip install --quiet --disable-pip-version-check -r requirements.txt
if [ ! -f .env ]; then
  cat > .env <<'ENV'
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.app.github.dev
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.app.github.dev
ENV
fi
python manage.py migrate --verbosity 0
python manage.py fasas_demo --skip-if-exists
