# Versione cloud: il FASAS su un dominio, con Supabase

Il FASAS gira in un solo container presso un servizio di hosting (esempio pronto: **Render**, file `deploy/render-cloud.yaml`),
risponde al dominio della struttura (es. `https://fasas.miacooperativa.it`) e tiene dati e file su **Supabase**
(database PostgreSQL e Storage). Nessun server in struttura, niente Redis né proxy da configurare.

```
browser / telefoni ──HTTPS──▶ dominio ──▶ servizio di hosting: container FASAS ──▶ Supabase (UE)
                                          · sito (gunicorn, file statici)          · PostgreSQL: dati
                                          · pianificatore dei job                  · Storage: file cifrati
                                                                                    · (bucket dei backup)
```

Per l'installazione su un PC in struttura resta valida [INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md); per
`fasas.online` su un server affittato (soluzione consigliata per i dati veri) [FASAS_ONLINE.md](FASAS_ONLINE.md).

## Cosa fa il FASAS da solo in modalità cloud (`FASAS_CLOUD=1`)

- A ogni avvio: aggiorna lo schema del database (`migrate`), protegge le tabelle dalle API di Supabase, crea il primo
  amministratore dalle variabili se non ce n'è nessuno, poi avvia sito e pianificatore.
- **Pianificatore integrato** al posto di Celery e Redis: stessi orari (chiusura turni, promemoria, backup alle 02:30,
  verifica dell'audit alle 02:00…). Se il servizio era fermo o addormentato, all'avvio recupera i job delle ultime 26
  ore; con due copie attive insieme (durante un aggiornamento) ogni job parte una volta sola.
- **File cifrati su Supabase Storage**: il FASAS cifra ogni documento prima di inviarlo; Supabase vede solo dati
  illeggibili. I documenti si aprono solo dal FASAS, con i controlli e l'audit di sempre.
- **Backup** cifrato ogni notte con database **e file dello Storage**, verificato e copiato fuori sede (passo 5).
- File statici serviti dal FASAS stesso; HTTPS obbligatorio, HSTS, cookie solo su HTTPS; risponde solo al dominio
  indicato. Il controllo `/salute/` risponde anche ai controlli interni del servizio di hosting.
- Se manca qualcosa di indispensabile (storage dei file, dominio, chiavi) **non parte** e il registro dice cosa manca.

## Costi (da decidere prima: nessun servizio a pagamento è attivato da questa configurazione)

| Servizio | Piano gratuito | Piano a pagamento |
|---|---|---|
| Supabase | progetto messo **in pausa** dopo 7 giorni di scarsa attività; **nessun backup giornaliero** di Supabase (resta quello del FASAS, passo 5) | Pro: mai in pausa, backup giornalieri di Supabase per 7 giorni |
| Render | il servizio **si addormenta** dopo un periodo senza visite: la prima pagina arriva in circa un minuto e i job girano solo da sveglio (al risveglio recupera quelli saltati) | Starter o superiore: sempre acceso |
| Dominio | quello che la struttura ha già | — |
| Copia fuori sede con blocco delle modifiche | bucket Supabase (incluso, senza blocco) | es. Backblaze B2 con Object Lock (gratuito fino a una soglia di spazio) |

`deploy/render-cloud.yaml` usa il piano **free**. Per l'uso reale con gli ospiti servono i piani sempre accesi: è una scelta
della struttura e si fa dal pannello di Render e di Supabase (prezzi correnti sui loro siti).

## Passo 1 – Chiavi (sul proprio PC)

Nella cartella del FASAS:

```bash
python manage.py fasas_genkey
```

Senza il FASAS installato basta Python:

```bash
python -c "import base64,os,secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50)); print('FASAS_ENCRYPTION_KEYS=' + base64.urlsafe_b64encode(os.urandom(32)).decode()); print('FASAS_BACKUP_KEY=' + base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

**FASAS_ENCRYPTION_KEYS e FASAS_BACKUP_KEY vanno stampate e chiuse nella busta di custodia**
([SICUREZZA.md](SICUREZZA.md)): senza di esse documenti e backup non si leggono più, nemmeno con l'accesso a Supabase.

## Passo 2 – Supabase: progetto e database

1. **Nuovo progetto dedicato al FASAS** (mai un progetto già usato da un'altra applicazione: il FASAS si rifiuta
   di partire se trova tabelle non sue, errore `fasas.E107`), regione **UE** (consigliata Francoforte,
   `eu-central-1`, la stessa di `deploy/render-cloud.yaml`). Il piano gratuito consente due progetti attivi. Annotare la password
   del database.
2. Applicare le migrazioni della cartella [`supabase/migrations`](../supabase/migrations), **nell'ordine**:
   - `…_fasas_schema_e_dati_iniziali.sql`: tabelle, vincoli, protezioni dell'audit, ruoli e permessi, configurazione
     iniziale (nessun dato personale, nessun utente);
   - `…_fasas_protezione_api.sql`: RLS su tutte le tabelle e nessun privilegio ai ruoli delle API di Supabase.

   Tre modi equivalenti: **SQL Editor** › New query › incollare il file › Run (poi il secondo); oppure `psql` con la
   stringa del punto 4:

   ```bash
   psql "postgresql://postgres.RIFERIMENTO:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:5432/postgres" -v ON_ERROR_STOP=1 --single-transaction -f supabase/migrations/20261106120000_fasas_schema_e_dati_iniziali.sql
   ```

   oppure la CLI di Supabase (`supabase init`, `supabase link` sul progetto, poi `supabase db push`).
   Se si salta questo passo il FASAS crea comunque tutto al primo avvio: le migrazioni servono a preparare e
   controllare il database prima.
3. **API automatiche di Supabase**: il FASAS non le usa. Nelle impostazioni del progetto, sezione Data API,
   disattivarle (o togliere `public` dagli schemi esposti). Anche lasciandole attive le tabelle restano chiuse
   (RLS senza policy e nessun privilegio), ma è meglio non esporle affatto.
4. **Stringa di connessione**: pulsante **Connect** › **Session pooler** (porta **5432**), sostituire la password.
   Non usare «Direct connection» (solo IPv6, molti servizi di hosting non la raggiungono) né il «Transaction pooler»
   (porta 6543: il backup con pg_dump non funziona).
5. **Mai** usare o copiare la chiave `service_role` (o «secret key»): il FASAS non ne ha bisogno.

## Passo 3 – Supabase: Storage per i documenti

1. Storage › **New bucket** `fasas-documenti`, **non pubblico**. Per la copia dei backup (passo 5, scelta A) un
   secondo bucket non pubblico `fasas-backup`.
2. Storage › Settings › **S3 Connection**: attivare la connessione S3, annotare **Endpoint** (es.
   `https://RIFERIMENTO.storage.supabase.co/storage/v1/s3`) e **Region**.
3. **New access key**: annotare Access key ID e Secret access key (il segreto si vede una volta sola). Sono chiavi
   solo per il server: non vanno mai in una pagina web o in un'app.

## Passo 4 – Render: il servizio

1. Render › **New** › **Blueprint** › repository del FASAS su GitHub, **Blueprint Path** `deploy/render-cloud.yaml`
   (il `render.yaml` della cartella principale è la versione di presentazione, [PRESENTAZIONE.md](PRESENTAZIONE.md)).
2. Compilare le variabili richieste (elenco completo e commentato in [`.env.cloud.example`](../.env.cloud.example)):
   chiavi del passo 1, `FASAS_DOMAIN`, `DATABASE_URL` (passo 2.4), `FASAS_S3_*` (passo 3), copia fuori sede
   (passo 5), `FASAS_ADMIN_USERNAME` e `FASAS_ADMIN_PASSWORD` (almeno 10 caratteri, non banale).
3. Avviare. Il primo avvio costruisce l'immagine (qualche minuto). Nel registro deve comparire
   `Amministratore … creato` e `Pianificatore avviato`.
4. **Dominio**: Settings › Custom Domains › aggiungere `fasas.miacooperativa.it`; presso chi gestisce il dominio
   creare il record DNS indicato da Render (di solito CNAME `fasas` → `NOME.onrender.com`). Il certificato HTTPS
   arriva da solo. `FASAS_DOMAIN` deve essere proprio quel nome.
5. Aggiornamenti: `deploy/render-cloud.yaml` non pubblica da solo a ogni modifica su GitHub. Dopo il collaudo di una nuova
   versione: **Manual Deploy**. Lo schema del database si aggiorna da solo all'avvio: non c'è SQL da eseguire.

Altri servizi che avviano un `Dockerfile` vanno bene allo stesso modo: stesse variabili, comando predefinito
dell'immagine, porta nella variabile `PORT`, controllo di salute `/salute/`. Sugli hosting Python senza Docker:
`scripts/avvia_cloud.sh` (serve anche `pg_dump` 17, altrimenti i backup non sono ripristinabili). Prima di sceglierne
uno controllare che non si addormenti e non abbia limiti di ore: a novembre 2026 Koyeb non offre più un piano
gratuito ai nuovi account e Oracle Always Free recupera le istanze poco usate ([FASAS_ONLINE.md](FASAS_ONLINE.md)).

## Passo 5 – Copia fuori sede dei backup

Il disco del container è temporaneo: il backup della notte va copiato fuori, altrimenti si perde al primo riavvio.

- **A – bucket Supabase `fasas-backup`** (nessun costo in più): `FASAS_OFFSITE_ENDPOINT`, `FASAS_OFFSITE_REGION`,
  `FASAS_OFFSITE_ACCESS_KEY`, `FASAS_OFFSITE_SECRET_KEY` uguali a quelli del passo 3, `FASAS_OFFSITE_BUCKET=fasas-backup`,
  `FASAS_OFFSITE_LOCK_DAYS=0`. Limite: Supabase Storage non ha il blocco delle modifiche e sta presso lo stesso
  fornitore del database.
- **B – object storage in UE con Object Lock** (es. Backblaze B2, consigliato per i dati veri): come in
  [BACKUP.md](BACKUP.md), `FASAS_OFFSITE_LOCK_DAYS=30`. Nessuno, nemmeno con le chiavi, può cancellare le copie
  prima della scadenza.

I backup sono cifrati con `FASAS_BACKUP_KEY` prima di uscire: il fornitore non li può leggere. Contengono database e
file dello Storage (i backup di Supabase, dove ci sono, contengono solo il database).

## Passo 6 – Primo accesso e controllo

1. Aprire `https://fasas.miacooperativa.it`, entrare con il gestore del sistema: il FASAS chiede subito la verifica in due
   passaggi (app sul telefono).
2. Togliere `FASAS_ADMIN_PASSWORD` dalle variabili di Render.
3. Sistema › **Pannello di sistema** e **Errori del sistema**: database, file (object storage), backup, audit e job
   in verde. La mattina dopo: Sistema › Backup mostra il backup delle 02:30 e la copia fuori sede.
4. Controllo dall'esterno (facoltativo, gratuito): un servizio di monitoraggio che chiama
   `https://fasas.miacooperativa.it/salute/` ([MONITORAGGIO.md](MONITORAGGIO.md)); il dettaglio solo con
   `FASAS_HEALTH_TOKEN` (generato da Render: lo si legge tra le variabili).

## Cosa cambia rispetto all'installazione in struttura

| Tema | In cloud |
|---|---|
| Disco di continuità, gruppo di continuità, VPN, disco USB mensile | Non servono: i rispettivi controlli restano spenti |
| Internet in struttura | Indispensabile. Se manca: modalità senza rete e foglio di emergenza ([PIANO_DI_CONTINUITA.md](PIANO_DI_CONTINUITA.md)); conviene una seconda linea (anche il telefono) |
| Accesso da fuori | Il FASAS è su internet: verifica in due passaggi obbligatoria per amministratore, coordinatore e medico (consigliata per tutti: `FASAS_2FA_REQUIRED_ROLES`) |
| Limitare l'accesso alla rete della struttura | Possibile con `FASAS_ALLOWED_NETWORKS` (IP pubblico della struttura); provarlo prima, perché blocca anche i telefoni fuori dal Wi-Fi |
| IP degli utenti nel registro degli accessi | Letto dall'intestazione del proxy del servizio di hosting (`FASAS_TRUSTED_PROXY_COUNT=1` predefinito in cloud). Se nel registro compare sempre lo stesso indirizzo per tutti, il servizio ha più proxy in fila: aumentare il numero |
| Prova di ripristino trimestrale | Parziale (controllo dell'archivio) se non c'è un secondo database vuoto in `FASAS_RESTORE_TEST_DATABASE_URL` |
| Ripristino completo | Su un progetto Supabase nuovo: `python manage.py backup_restore --confirm FILE` con le variabili del nuovo progetto; i file tornano nel bucket indicato da `FASAS_S3_BUCKET` |
| Firma con CIE | Uguale: l'app FASAS Signer si collega al dominio HTTPS |

## Sicurezza e GDPR

- Supabase e il servizio di hosting trattano dati sanitari per conto della struttura: prima dei dati veri firmare i
  loro accordi sul trattamento (art. 28, [gdpr/RESPONSABILI_E_NOMINE.md](gdpr/RESPONSABILI_E_NOMINE.md)), scegliere
  regioni UE, aggiornare registro dei trattamenti e DPIA e far valutare al DPO le garanzie sui trasferimenti
  (fornitori con sede fuori dall'UE).
- I file sono cifrati dal FASAS; il contenuto del database no (Supabase cifra i dischi). Chi entra nel pannello di
  Supabase o di Render vede i dati: account personali con verifica in due passaggi, pochi amministratori.
- Le chiavi stanno solo nelle variabili del servizio e nella busta di custodia, mai nel repository (che è pubblico).
- Tabelle chiuse alle API di Supabase (RLS senza policy, nessun privilegio ad `anon`, `authenticated`,
  `service_role`); il FASAS lo ricontrolla a ogni avvio.

## Problemi comuni

| Messaggio nel registro | Causa |
|---|---|
| `fasas.E102` / `fasas.E103` | Mancano o sono incomplete le variabili `FASAS_S3_*` |
| `fasas.E104` | Manca `FASAS_DOMAIN` |
| `fasas.E106` | Mancano `FASAS_ENCRYPTION_KEYS` o `FASAS_BACKUP_KEY` |
| `fasas.E107` | Il database contiene tabelle di un'altra applicazione: usare un progetto Supabase nuovo solo per il FASAS (nulla è stato creato o modificato) |
| La pagina rimanda sempre a un altro indirizzo | Il primo nome di `FASAS_DOMAIN` è il dominio principale: `www` e il nome tecnico dell'hosting rimandano lì |
| `password authentication failed` | Password sbagliata in `DATABASE_URL`; caratteri come `@ : / #` vanno scritti come `%40 %3A %2F %23` |
| `Network is unreachable` verso `db.….supabase.co` | Si sta usando «Direct connection»: usare «Session pooler» |
| Pagina «Bad Request (400)» | Il nome nella barra degli indirizzi non è in `FASAS_DOMAIN` |
| Errore CSRF (403) dopo l'accesso | Si apre il sito con un nome diverso da `FASAS_DOMAIN` o senza HTTPS |
| Il caricamento di un documento fallisce | Bucket inesistente o chiavi S3 sbagliate (Sistema › Errori del sistema) |

## Come è stato provato

- In locale: migrazioni SQL su un PostgreSQL con i ruoli e i privilegi predefiniti di Supabase, avvio completo in
  modalità cloud con uno storage S3 di prova, accesso, caricamento e scaricamento di un documento finto, job
  recuperati all'avvio, backup con i file dello storage, copia fuori sede, ripristino.
- Nella CI di GitHub (job «cloud»), a ogni modifica: le stesse prove con l'immagine ufficiale del PostgreSQL di
  Supabase e con l'immagine Docker del FASAS.
- Non provati da qui: un account Render e un progetto Supabase veri (DNS, certificato, pooler, Storage reale). Il
  primo avvio va controllato con il passo 6 prima di inserire dati reali.

## Per chi sviluppa

- Orari dei job: `fasas/core/scheduler.py` (usati anche da Celery). Avvio: `docker/cloud.sh`.
- Nuove migrazioni di Django: la versione cloud le applica da sola all'avvio. Per rigenerare i file SQL di un
  progetto nuovo: `python scripts/genera_migrazioni_supabase.py postgres://…/database_vuoto` (il test
  `MigrazioniSupabaseTest` segnala quando servono).
- Prova completa su un servizio avviato: `python scripts/prova_cloud.py NUMERO_OSPITE_DI_PROVA` (variabili in testa
  allo script).
