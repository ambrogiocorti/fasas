# Backup, copia fuori sede e prova di ripristino

Ogni notte il FASAS fa un backup cifrato, lo verifica, ne copia una versione fuori sede che nessuno può cancellare per
30 giorni e conserva i punti di controllo dell'audit. Ogni tre mesi riapre l'ultimo backup in un database separato e
ne lascia il verbale.

## Cosa succede ogni notte

| Ora | Job | Cosa fa |
|---|---|---|
| 02:00 | `audit_verify` | verifica tutta la catena dell'audit e salva un punto di controllo (con marca temporale se c'è una TSA) |
| 02:30 | `backup` | backup cifrato AES-256-GCM (database, file, punti di controllo), verifica, copia fuori sede, pulizia |
| 1° gennaio, aprile, luglio, ottobre, 04:15 | `restore_test` | prova di ripristino con verbale |

Con cron al posto di Celery: `python manage.py fasas_jobs audit_verify backup` ogni notte e
`python manage.py backup_prova_ripristino` ogni tre mesi.

## Copia fuori sede (object storage compatibile S3, in UE)

1. Scegliere un fornitore con data center in UE che supporti **Object Lock** (contratto art. 28; il fornitore
   riceve solo file cifrati, la chiave resta alla comunità).
2. Creare un bucket **con Object Lock attivo** (si imposta solo alla creazione) e una chiave d'accesso limitata a
   quel bucket.
3. Nel `.env`:

```
FASAS_OFFSITE_ENDPOINT=https://s3.<regione>.<fornitore>
FASAS_OFFSITE_REGION=<regione>
FASAS_OFFSITE_BUCKET=<nome del bucket>
FASAS_OFFSITE_ACCESS_KEY=<chiave d'accesso>
FASAS_OFFSITE_SECRET_KEY_FILE=/etc/fasas/offsite-secret   # oppure FASAS_OFFSITE_SECRET_KEY=...
FASAS_OFFSITE_LOCK_DAYS=30
FASAS_OFFSITE_KEEP_DAILY=30
FASAS_OFFSITE_KEEP_MONTHLY=12
```

4. Dalla pagina *Backup* premere «Esegui backup ora»: la colonna «Fuori sede» deve indicare «copiato» e la data
   di fine blocco. Un errore di copia avvisa l'amministratore e non tocca il backup locale.

Il blocco in modalità `COMPLIANCE` impedisce a chiunque, anche a chi ha le credenziali o a un ransomware, di cancellare
o sovrascrivere la copia prima della scadenza. Le copie oltre la conservazione (30 giornaliere + 12 mensili) si
cancellano da sole quando il blocco è scaduto.

## Prova di ripristino

Dalla pagina *Backup* › «Prova di ripristino», oppure `python manage.py backup_prova_ripristino`:

1. prende l'ultimo backup, dalla copia fuori sede se c'è (lo scenario di un disastro), altrimenti dal server;
2. controlla l'impronta registrata al caricamento, decifra e verifica ogni componente;
3. lo ripristina **in un database separato**, mai in quello in uso: SQLite temporaneo per i backup JSON,
   `FASAS_RESTORE_TEST_DATABASE_URL` (database vuoto) per i backup PostgreSQL; senza, la prova è «parziale»;
4. verifica l'audit log ripristinato e conta i dati principali;
5. salva il verbale stampabile, da firmare e archiviare. Un esito negativo avvisa l'amministratore.

Il `docker compose` crea già il database `fasas_prova_ripristino` per la prova.

## Ripristino vero (disastro)

Con l'applicazione ferma: `python manage.py backup_restore <file.fbk> --confirm`, poi `python manage.py audit_verify`.
Servono la chiave `FASAS_BACKUP_KEY` (busta di custodia: `python manage.py fasas_chiavi apri <busta>`) e, per i
documenti, `FASAS_ENCRYPTION_KEYS`. Il ripristino funziona anche verso un PostgreSQL di versione precedente a quella
del `pg_dump` (es. Supabase su PostgreSQL 15).
