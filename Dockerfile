# FASAS Digitale – immagine dell'applicazione (Django + gunicorn + Celery). Guida: docs/CONTAINER.md
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASAS_MEDIA_ROOT=/data/media FASAS_BACKUP_DIR=/data/backups

# Client PostgreSQL 17 dal repository ufficiale: pg_dump deve avere versione uguale o superiore al server
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10001 --create-home --home-dir /home/fasas fasas \
 && install -d -o fasas -g fasas -m 700 /data /data/media /data/backups \
 && install -d -o fasas -g fasas /static

WORKDIR /app
COPY requirements.lock .
RUN pip install --require-hashes -r requirements.lock
COPY --chown=fasas:fasas . .
RUN DJANGO_SECRET_KEY=solo-per-collectstatic DJANGO_DEBUG=0 python manage.py collectstatic --noinput --verbosity 0

USER fasas
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/salute/', timeout=8)" || exit 1
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]
