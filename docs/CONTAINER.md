# Installazione con Docker

Un solo comando avvia database, sito, job periodici e proxy HTTPS con certificato automatico. È l'installazione
consigliata per una nuova comunità e per l'ambiente di prova.

> Per installarlo su un PC della struttura senza costi (Ubuntu Server, indirizzo DuckDNS, backup su Backblaze B2 e
> disco USB), con lista della spesa e script che prepara tutto: [INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md).

## Servizi

| Servizio | Immagine | Ruolo |
|---|---|---|
| `db` | `postgres:17` (variabile `FASAS_POSTGRES_IMAGE`) | database; crea anche il database vuoto per la prova di ripristino |
| `redis` | `redis:7-alpine` | coda dei job |
| `web` | immagine del FASAS | applica le migrazioni e avvia il sito (gunicorn) |
| `worker` | immagine del FASAS | job periodici (Celery con scheduler integrato) |
| `proxy` | `caddy:2` | HTTPS con certificato Let's Encrypt per `FASAS_DOMAIN`, file statici |

L'immagine del FASAS gira con un utente non privilegiato, installa le dipendenze con le impronte di
`requirements.lock`, contiene il client PostgreSQL 17 per i backup e un controllo di salute.

## Installazione

1. Server Linux con Docker, dominio che punta al server, porte 80 e 443 aperte.
2. `cp .env.example .env` e compilare: `DJANGO_SECRET_KEY`, `FASAS_ENCRYPTION_KEYS`, `FASAS_BACKUP_KEY` (generarle
   con `python manage.py fasas_genkey` o con `docker compose run --rm web python manage.py fasas_genkey`),
   `POSTGRES_PASSWORD`, `FASAS_DOMAIN`, `FASAS_HEALTH_TOKEN`.
3. Avvio:

```bash
docker compose up -d --build
```

4. Primo amministratore:

```bash
docker compose exec web python manage.py createsuperuser
```

5. Busta di custodia delle chiavi, da conservare fuori dal server:

```bash
docker compose exec web python manage.py fasas_chiavi busta /data/busta-chiavi.fkey
```

## Ambiente di prova separato

Su un secondo server (o con un altro nome di progetto `-p fasas-prova` e un altro dominio) con dati di fantasia:

```bash
docker compose -p fasas-prova up -d --build
```

```bash
docker compose -p fasas-prova exec web python manage.py fasas_demo --ambiente-di-prova
```

Ogni nuova versione si installa prima qui; in produzione solo dopo il collaudo (vedi CHANGELOG.md).

## Aggiornamento

```bash
git pull && docker compose up -d --build
```

Le migrazioni partono da sole all'avvio di `web`. I dati restano nei volumi `fasas-db` e `fasas-data`.

## Verifica

La CI di GitHub costruisce l'immagine, avvia tutto il compose, fa un backup con `pg_dump` e una prova di ripristino
a ogni modifica (job «container»).
