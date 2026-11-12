# Prestazioni e prova di carico

Il FASAS regge senza problemi una RSD da 60 posti con 20 operatori collegati insieme: con 20 operatori
contemporanei il 95% delle pagine risponde in meno di 0,6 secondi, senza errori.

## Risultati (31/10/2026)

Ambiente: gunicorn con 3 processi (come in [DEPLOY.md](DEPLOY.md)), PostgreSQL 16, impostazioni di produzione
(`DJANGO_DEBUG=0`), macchina da 4 CPU che ospitava anche il generatore di carico. Dati di fantasia: 60 ospiti,
3 terapie ciascuno, 30 giorni di storico (16.200 somministrazioni, 3.600 parametri, 3.600 voci di diario).
Ogni operatore virtuale ripete: cruscotto, elenco ospiti, cartella, giro farmaci, contatore notifiche e ogni tre
giri una rilevazione di parametri, con 0,5–1,5 secondi di pausa tra un giro e l'altro.

| Operatori contemporanei | Richieste al secondo | Cruscotto (mediana / 95%) | Giro farmaci (mediana / 95%) | Salvataggio parametri (mediana / 95%) | Errori |
|---|---|---|---|---|---|
| 5 | 18 | 147 / 223 ms | 143 / 212 ms | 26 / 62 ms | 0 |
| 20 | 37 | 365 / 572 ms | 376 / 550 ms | 239 / 410 ms | 0 |

## Difetto trovato e corretto

La prima prova, con soli 5 operatori, dava 4 secondi per il cruscotto e 2 per il giro farmaci. La causa: la
configurazione dei turni veniva riletta dal database a ogni calcolo del turno, cioè 1.807 volte per un solo
cruscotto. Ora configurazione e comunità si leggono una volta per richiesta (e per job), e anche evacuazioni,
tag e allergie si leggono con una sola query per tutti gli ospiti:

| Pagina | Prima | Dopo |
|---|---|---|
| Cruscotto dell'operatore | 3.714 query, 4,5 s | 43 query, 0,13 s |
| Giro farmaci | 2.004 query, 2,1 s | 20 query, 0,17 s |

## Ripetere la prova

Solo su un'installazione di prova con dati di fantasia, mai in produzione:

```bash
DJANGO_DEBUG=1 python manage.py fasas_dati_carico --ospiti 60 --operatori 20
```

```bash
python scripts/prova_carico.py --url http://127.0.0.1:8000 --utenti 20 --durata 60
```

Per numeri realistici avviare il sito con gunicorn e `DJANGO_DEBUG=0` (con `DEBUG` attivo Django registra ogni
query e rallenta). Oltre i 20 operatori contemporanei aumentare i processi gunicorn (`GUNICORN_WORKERS`) e le CPU.
