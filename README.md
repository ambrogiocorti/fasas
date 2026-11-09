# FASAS Digitale

Sistema web per la gestione del **FASAS** (Fascicolo Socio Assistenziale Sanitario) di una comunità
per persone con disabilità. Sostituisce il fascicolo cartaceo con una cartella digitale per ogni ospite,
tracciata in ogni modifica, cifrata a riposo e organizzata attorno al lavoro reale dei turni.

> **Stato:** versione 0.9.0 per il pilota più le novità non ancora rilasciate ([CHANGELOG](CHANGELOG.md)); oltre 300
> test automatici che passano su SQLite, PostgreSQL e Windows, più la prova completa del container e dello script
> di installazione. **Non ancora collaudato in una comunità reale**: prima dei dati veri servono i passaggi di
> [Prima della messa in produzione](#prima-della-messa-in-produzione).

## Cosa fa

| Area | Funzioni |
|---|---|
| **Cartella ospite** | anagrafica, tutela legale e contatti, diagnosi, allergie/intolleranze, dieta, disabilità, tag clinici con avvisi; cruscotto clinico; storico completo |
| **Terapie** | prescrizioni con orari e vie, giro farmaci per turno, farmaci SOS con motivo, limiti e validazione; stessi controlli da pagina web, telefono senza rete e API |
| **Magazzino farmaci** | lotti con scadenza, scorta personale o comune, scarico automatico a ogni somministrazione, avvisi di esaurimento e scadenza |
| **Parametri e scale** | parametri configurabili con grafici; scale di valutazione (Barthel, Braden, Norton, Tinetti, PAINAD, NRS) con data della prossima rivalutazione e promemoria |
| **Lesioni e medicazioni** | lesioni da pressione e altre ferite con categoria, misure e foto cifrate; piano di medicazione, medicazioni da fare oggi, avvisi di ritardo |
| **Eventi e contenzioni** | cadute, crisi, agitazione, interventi; contenzioni con autorizzazione medica; pulsante **«Evento critico»** sempre visibile |
| **Turno** | registro giornaliero, evacuazioni (avvenuta / non avvenuta / non documentata / assenza), diario, checklist del turno, chiusura del turno |
| **Protocolli** | evacuazione, febbre, glicemia, crisi, agitazione, SOS: soglie con campi guidati validate dal medico, azioni previste da spuntare |
| **PAI** | aree, obiettivi, interventi, verifiche, versioni; ultime valutazioni e lesioni aperte; PDF archiviato e firmabile |
| **Visite, documenti, report** | appuntamenti con promemoria; documenti cifrati e versionati; report PDF/Excel configurabili e programmabili; esportazione della cartella completa |
| **Firma** | firma remota del medico con il certificato qualificato del proprio prestatore (API CSC: nascosta finché non è configurata, da provare nella sandbox del prestatore); firma con CIE predisposta ma **spenta** fino a parere legale, polizza e prova con CIE vere |
| **Sicurezza** | ruoli e permessi per utente, verifica in due passaggi, audit log a catena di hash con punti di controllo marcati, blocco delle modifiche, log accessi, backup cifrati con copia fuori sede immutabile |
| **Amministrazione** | presenze per la rendicontazione, rette e prospetti; turni del personale con ferie e cambi turno |
| **Senza rete** | giro farmaci, SOS, parametri, diario ed eventi registrabili durante un'interruzione e sincronizzati dopo; foglio di emergenza stampabile |

Corrispondenza tra specifica e codice: [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md). Guide d'uso di una pagina per
ruolo: [operatore](docs/guide/OPERATORE.md), [coordinatore](docs/guide/COORDINATORE.md), [medico](docs/guide/MEDICO.md),
[amministrativo](docs/guide/AMMINISTRATIVO.md).

## Provarlo con dati di fantasia

Si entra con `admin`, `coordinatore`, `operatore`, `medico` o `amministrativo`, password `Demo-Fasas-2026!`.
**Non inserire dati di persone reali**: la versione di prova usa chiavi pubbliche e lo segnala con una fascia rossa.

- **Nel browser, senza installare nulla**: su GitHub *Code → Codespaces → Create codespace* sul branch di lavoro; il
  sistema si avvia da solo (porta 8000). Circa 60 ore al mese gratuite con un account personale.
- **Sul proprio PC**: installare [Python](https://www.python.org/downloads/) e [Git](https://git-scm.com/downloads), poi

  ```bash
  git clone -b claude/fasas-digital-system-5v69px https://github.com/ambrogiocorti/fasas.git
  ```

  e da lì in poi doppio clic su `avvia.bat` (Windows) o `./avvia.sh` (Mac/Linux): aggiorna, controlla che nel
  database ci siano solo dati di fantasia e apre il browser.

## Installazione in struttura

**Una sola guida**: [docs/INSTALLAZIONE_IN_STRUTTURA.md](docs/INSTALLAZIONE_IN_STRUTTURA.md) – PC dedicato con
Ubuntu Server e disco cifrato, Docker (database PostgreSQL, job, HTTPS), indirizzo DuckDNS, copia fuori sede su
Backblaze B2 nel piano gratuito, gruppo di continuità; con lista della spesa e calendario di manutenzione. Lo script
`scripts/prepara_server.sh` fa la parte tecnica ed è provato a ogni modifica nella CI; la manutenzione del mese è
`scripts/aggiorna_fasas.sh`, anche da casa con la VPN dell'amministratore (`scripts/accesso_remoto.sh`).

## Presentazione online (dati inventati)

Una copia del FASAS su internet per mostrarlo e provarlo, gratuita e **senza carta di credito**: account gratuito di
PythonAnywhere e un solo comando (`scripts/presentazione_pythonanywhere.sh`), oppure GitHub Codespaces per una
presentazione dal vivo. Dati di esempio, mai dati reali: [docs/PRESENTAZIONE.md](docs/PRESENTAZIONE.md).

## Versione online (fasas.online)

Server affittato in UE con lo stesso stack Docker, dominio `fasas.online`, HTTPS automatico, pubblicazione da GitHub
Actions con ritorno automatico alla versione precedente: [docs/FASAS_ONLINE.md](docs/FASAS_ONLINE.md)
(`scripts/prepara_server.sh --vps`, workflow «Pubblica su fasas.online»).

## Versione cloud (dominio + Supabase)

Senza server da gestire: [docs/CLOUD.md](docs/CLOUD.md). Un container presso un servizio di hosting (pronto
`deploy/render-cloud.yaml` per Render), il dominio della struttura, database e file cifrati su Supabase con le migrazioni SQL in
[`supabase/migrations`](supabase/migrations). Sito e job nello stesso container (`FASAS_CLOUD=1`), senza Redis.

Riferimenti tecnici per chi installa diversamente: [docs/CONTAINER.md](docs/CONTAINER.md) (Docker su un altro server),
[docs/DEPLOY.md](docs/DEPLOY.md) (installazione tradizionale senza Docker, anche con un database gestito).

## Sviluppo

Requisiti: Python 3.12+. Senza `DATABASE_URL` si usa SQLite.

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
python manage.py migrate
```

```bash
python manage.py fasas_demo
```

```bash
python manage.py runserver
```

Test: `python manage.py test fasas.tests` (a ogni modifica anche nella scheda **Actions** di GitHub).

| Comando | A cosa serve |
|---|---|
| `python manage.py fasas_setup` | ruoli, permessi e configurazioni predefinite (anche in automatico dopo `migrate`) |
| `python manage.py fasas_genkey` | genera `DJANGO_SECRET_KEY`, `FASAS_ENCRYPTION_KEYS`, `FASAS_BACKUP_KEY` |
| `python manage.py fasas_jobs --list` | job periodici; `fasas_jobs all` li esegue tutti (escluso il backup) |
| `python manage.py backup_create` / `backup_verify` / `backup_restore FILE --confirm` | backup cifrato, verifica, ripristino |
| `python manage.py audit_verify` | integrità della catena di hash dell'audit log |

```
config/              impostazioni, URL, Celery
fasas/core           comunità, configurazione, turni, blocco modifiche, cifratura, job, monitoraggio
fasas/accounts       utenti, ruoli, permessi, verifica in due passaggi, log accessi
fasas/audit          audit log in sola aggiunta con catena di hash e punti di controllo
fasas/guests         ospiti, tag, contatti, diagnosi, allergie, archiviazione, storico
fasas/clinical       terapie, somministrazioni, SOS, parametri, eventi, contenzioni, emergenza
fasas/assessments    scale di valutazione e rivalutazioni
fasas/wounds         lesioni, rilevazioni con foto, piani di medicazione, medicazioni
fasas/pharmacy       farmaci, interazioni, lotti, movimenti
fasas/daily          registro, evacuazioni, diario, checklist, chiusura turni
fasas/protocols      protocolli automatici
fasas/appointments   visite e promemoria
fasas/pai            Piano Assistenziale Individuale
fasas/documents      documenti cifrati e versionati
fasas/signatures     firma PAdES remota, firma con CIE, verifica
fasas/notifications  notifiche e push
fasas/reports        report, modelli di report, esportazione cartella
fasas/backups        backup cifrati, copia fuori sede, prova di ripristino
fasas/billing        presenze, rette, prospetti
fasas/staffing       turni del personale
fasas/imports        importazione dal cartaceo
fasas/offline        lavoro senza rete
fasas/search         ricerca
fasas/api            API REST (spenta per default)
signer/, mobile/     FASAS Signer per computer e prototipi Android/iOS (congelati, non collaudati con una CIE)
```

## Prima della messa in produzione

Cosa fa la struttura, chi lo fa e con quali modelli già pronti: [docs/ADEMPIMENTI_PRIMA_DELL_AVVIO.md](docs/ADEMPIMENTI_PRIMA_DELL_AVVIO.md).
In breve:

1. **Privacy**: DPO, registro dei trattamenti, DPIA, informative, nomine e autorizzazioni ([docs/gdpr/](docs/gdpr/README.md)).
2. **Validazione clinica**: il medico valida soglie e azioni dei protocolli e sceglie la regola sui limiti dei SOS.
3. **Dispositivo medico**: parere di un consulente regolatorio sui promemoria ([docs/DISPOSITIVO_MEDICO.md](docs/DISPOSITIVO_MEDICO.md)).
4. **ATS**: presentazione del fascicolo digitale ([docs/gdpr/CHECKLIST_ATS.md](docs/gdpr/CHECKLIST_ATS.md)).
5. **Sicurezza fisica e continuità**: locale chiuso, chiavi in cassaforte, sostituto addestrato
   ([docs/SICUREZZA_FISICA_E_CONTINUITA.md](docs/SICUREZZA_FISICA_E_CONTINUITA.md)).
6. **Test di sicurezza esterno** e **pilota di 2–4 settimane** accanto alla carta.

Stato dei lavori: [docs/ROADMAP.md](docs/ROADMAP.md).

## Crediti

Le icone derivano da [Lucide](https://lucide.dev) (licenza ISC) e sono incluse nel progetto
(`templates/partials/icons.html`): l'applicazione non carica risorse esterne.
