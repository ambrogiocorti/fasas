# Installazione in produzione

Architettura consigliata per una comunità (10–100 ospiti):

```
Operatori (browser / tablet) ──HTTPS──► nginx ──► gunicorn (Django) ──TLS──► Supabase PostgreSQL (regione UE)
                                                     │
                                      Celery worker + beat ◄── Redis
                                                     │
                                   /var/lib/fasas/media (file cifrati)   /var/lib/fasas/backups (backup cifrati)
```

Un piccolo server Linux (2 vCPU, 4 GB RAM) è sufficiente. In alternativa a Celery i job possono girare da cron.

## 1. Database su Supabase

1. Creare un progetto Supabase in una **regione UE** (es. Francoforte) e firmare il DPA (accordo sul trattamento dei dati).
2. In *Project Settings → Database* copiare la stringa di connessione in modalità **Session** (porta 5432) o la
   connessione diretta. Non usare la modalità *Transaction* (porta 6543): Django usa connessioni persistenti e lock di sessione.
3. Impostare `DATABASE_URL` e `DATABASE_SSL_REQUIRE=1` nel file `.env`.
4. FASAS non usa le API REST di Supabase: dopo ogni `migrate` attiva automaticamente la Row Level Security su tutte
   le tabelle e revoca i privilegi ai ruoli `anon` e `authenticated` (si può rilanciare con `manage.py supabase_harden`).
   Non pubblicare comunque la chiave `service_role`.
5. Per i backup con `pg_dump` installare un client PostgreSQL della **stessa versione o superiore** a quella del progetto
   Supabase (es. `postgresql-client-17`). Se `pg_dump` non è disponibile il backup usa un export JSON di Django.

## 2. Applicazione

```bash
sudo useradd --system --home /opt/fasas fasas
```

```bash
sudo mkdir -p /var/lib/fasas/media /var/lib/fasas/backups && sudo chown -R fasas: /var/lib/fasas && sudo chmod 700 /var/lib/fasas/*
```

```bash
sudo -u fasas git clone https://github.com/ambrogiocorti/fasas /opt/fasas/app
```

```bash
cd /opt/fasas/app && sudo -u fasas python3 -m venv .venv && sudo -u fasas .venv/bin/pip install -r requirements.txt
```

```bash
sudo -u fasas .venv/bin/python manage.py fasas_genkey
```

Copiare `.env.example` in `.env`, inserire le chiavi generate e i dati del database, poi:

```bash
sudo -u fasas .venv/bin/python manage.py migrate
```

```bash
sudo -u fasas .venv/bin/python manage.py collectstatic --noinput
```

```bash
sudo -u fasas .venv/bin/python manage.py createsuperuser
```

Accedere con il superuser, impostare il nome della comunità in *Impostazioni → Configurazione generale* e creare gli
utenti con il loro ruolo. Il superuser va usato solo per la manutenzione: per il lavoro quotidiano creare un utente
con ruolo *Amministratore*.

### systemd

`/etc/systemd/system/fasas.service`

```ini
[Unit]
Description=FASAS Digitale
After=network.target

[Service]
User=fasas
WorkingDirectory=/opt/fasas/app
ExecStart=/opt/fasas/app/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/fasas-celery.service`

```ini
[Unit]
Description=FASAS job pianificati
After=network.target redis.service

[Service]
User=fasas
WorkingDirectory=/opt/fasas/app
ExecStart=/opt/fasas/app/.venv/bin/celery -A config worker --beat --concurrency 2 --loglevel INFO
Restart=always

[Install]
WantedBy=multi-user.target
```

In alternativa a Celery, un crontab dell'utente `fasas`:

```
*/15 * * * *  cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs close_shifts
*/30 * * * *  cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs protocols
5 * * * *     cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs appointments
10 6,18 * * * cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs stock
0 7 * * *     cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs documents pai_reviews
15 1 * * *    cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs reports report_retention
30 2 * * *    cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs backup
30 3 * * *    cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs audit_verify
50 3 * * *    cd /opt/fasas/app && .venv/bin/python manage.py fasas_jobs imports_cleanup
```

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name fasas.esempio.it;
    ssl_certificate     /etc/letsencrypt/live/fasas.esempio.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fasas.esempio.it/privkey.pem;
    client_max_body_size 25m;   # >= dimensione massima file configurata

    # facoltativo: accesso solo dalla rete della comunità / VPN
    # allow 192.168.10.0/24; deny all;

    location /static/ { alias /opt/fasas/app/staticfiles/; expires 7d; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Non esporre mai la cartella `media`: i file sono serviti solo dall'applicazione dopo il controllo dei permessi.

## 3. Backup e ripristino

- Il job `backup` crea ogni notte un file `.fbk` cifrato in `FASAS_BACKUP_DIR`, lo verifica e applica la conservazione
  configurata (default 30 giorni, l'ultimo backup verificato non viene mai eliminato).
- **Copiare i backup fuori dal server** (es. `rclone` verso uno storage S3 europeo con versioning): il file è già cifrato.
- Supabase effettua anche i propri backup del database (piani a pagamento): sono complementari, non sostitutivi,
  perché non comprendono i documenti.
- Ripristino (applicazione ferma, database di destinazione vuoto e raggiungibile):

```bash
.venv/bin/python manage.py backup_restore /percorso/fasas-backup-AAAAMMGG-HHMMSS-N.fbk --confirm
```

```bash
.venv/bin/python manage.py audit_verify
```

Provare il ripristino su un database di prova almeno ogni sei mesi.

## 4. Aggiornamenti

```bash
cd /opt/fasas/app && sudo -u fasas git pull && sudo -u fasas .venv/bin/pip install -r requirements.txt
```

```bash
sudo -u fasas .venv/bin/python manage.py migrate && sudo -u fasas .venv/bin/python manage.py collectstatic --noinput
```

```bash
sudo systemctl restart fasas fasas-celery
```

Eseguire un backup manuale (`manage.py backup_create`) prima di ogni aggiornamento.
