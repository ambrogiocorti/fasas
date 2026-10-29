# FASAS Digitale

Sistema web per la gestione del **FASAS** (Fascicolo Socio Assistenziale Sanitario) di una comunità
per persone con disabilità. Sostituisce il fascicolo cartaceo con una cartella digitale per ogni ospite,
tracciata in ogni modifica, cifrata a riposo e organizzata attorno al lavoro reale dei turni.

> **Stato:** prima versione completa e funzionante, con 67 test automatici che passano su SQLite e PostgreSQL.
> Prima dell'uso con dati reali servono le verifiche descritte in [Prima della messa in produzione](#prima-della-messa-in-produzione).

## Cosa fa

| Area | Funzioni |
|---|---|
| **Cartella ospite** | anagrafica, tutela legale e contatti, diagnosi, allergie/intolleranze, dieta, disabilità, tag clinici con avvisi; cruscotto clinico; storico completo (timeline) |
| **Terapie** | prescrizioni con orari e vie di somministrazione, giro farmaci per turno, farmaci SOS con motivo, limiti e validazione, controllo automatico di duplicati, interazioni e allergie |
| **Magazzino farmaci** | lotti con scadenza, farmaci personali dell'ospite o scorta comune, scarico automatico FEFO a ogni somministrazione, soglie minime, avvisi di esaurimento e scadenza |
| **Parametri** | temperatura, pressione, glicemia, peso e altri configurabili, valori fuori range evidenziati, grafici nel tempo |
| **Eventi e contenzioni** | cadute, crisi, agitazione, interventi, incidenti; contenzioni con autorizzazione medica, durata e responsabile; **pulsante «Evento critico»** sempre visibile |
| **Turno** | registro giornaliero (pasti, igiene, comportamento, attività), evacuazioni in modalità A (SI/NO giornaliero) o B (solo quando avviene) con conteggio dei giorni, diario assistenziale, checklist per turno (✔ completato / ⚠ mancante), registro turni operatori |
| **Protocolli automatici** | evacuazione, febbre, glicemia, crisi epilettica, agitazione, farmaci SOS: notifica, avviso in cruscotto e lista delle azioni richieste da spuntare |
| **PAI** | aree sanitaria, autonomia, comportamentale, sociale; obiettivi, interventi, responsabili, verifiche; versioni e revisioni; PDF archiviato e firmabile |
| **Visite** | appuntamenti con accompagnatore, esito e referto; promemoria «visita domani» e «visita oggi» |
| **Documenti** | carta d'identità, tessera sanitaria, certificati, consensi, relazioni, PAI: cifrati, versionati, con limite di dimensione e registro degli accessi |
| **Firma digitale** | firma remota qualificata del medico tramite API CSC del prestatore (PIN + OTP da app o SMS) o certificato PKCS#12; PAdES B-B/B-T/B-LT/B-LTA con marca temporale; verifica delle firme – guida in [docs/FIRMA_DIGITALE.md](docs/FIRMA_DIGITALE.md) |
| **Report** | registro giornaliero, farmaci, eventi, parametri, protocolli in PDF ed Excel, su richiesta o programmati (giornalieri, settimanali, mensili), conservati 1–5 anni |
| **Esportazione cartella** | PDF unico con tutta la cartella e gli allegati, per il trasferimento dell'ospite |
| **Sicurezza e tracciabilità** | ruoli e permessi granulari per utente, audit log non cancellabile con catena di hash, blocco delle modifiche (24 h / motivazione / solo coordinatore), chiusura del turno, cartelle archiviate in sola lettura, log accessi con IP e dispositivo, blocco dopo tentativi falliti, disconnessione per inattività, restrizione per rete |
| **Passaggio dal cartaceo** | modello Excel per anagrafiche, contatti, diagnosi, allergie, terapie in corso e giacenze con anteprima degli errori; caricamento massivo dei documenti scansionati abbinati all'ospite – guida in [docs/IMPORTAZIONE.md](docs/IMPORTAZIONE.md) |
| **Telefono e senza rete** | installabile come app; notifiche push sul telefono senza dati sanitari sulla schermata di blocco; modalità senza rete cifrata per giro farmaci, SOS, parametri, diario ed eventi con sincronizzazione automatica; foglio di emergenza stampabile – [docs/NOTIFICHE_E_SENZA_RETE.md](docs/NOTIFICHE_E_SENZA_RETE.md) |
| **Presenze e rette** | presenze giornaliere ricavate dai movimenti, chiusura mensile per la rendicontazione con export Excel; rette per pagante con percentuali per le assenze; prospetti numerati in PDF ed Excel, incassi e scaduti; ruolo Amministrativo senza accesso alla cartella clinica – [docs/PRESENZE_E_RETTE.md](docs/PRESENZE_E_RETTE.md) |
| **Continuità** | backup giornaliero cifrato AES-256-GCM con verifica di integrità e ripristino |
| **Altro** | ricerca globale con filtri, notifiche configurabili per ruolo, tema scuro (automatico nel turno di notte), interfaccia utilizzabile da tablet e smartphone, API REST per una futura app mobile |

La corrispondenza puntuale tra i 30 punti della specifica e il codice è in [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md).

## Provare il sistema

Tre modi, dal più semplice. In tutti si entra con `admin`, `coordinatore`, `operatore`, `medico` o `amministrativo`,
password `Demo-Fasas-2026!`, su dati di fantasia. **Non inserire dati reali di ospiti in queste prove.**
Ogni ruolo ha un cruscotto e un menu diversi: l'operatore vede *Il mio turno*, il coordinatore *Coordinamento*,
il medico *Area medica*, l'amministratore il *Pannello di sistema* e l'amministrativo *Amministrazione*
(questi ultimi due senza accesso alle cartelle cliniche).
Dettagli in [docs/SICUREZZA.md](docs/SICUREZZA.md#ruoli-e-permessi).

### 1. Nel browser, senza installare nulla (GitHub Codespaces)

1. Su GitHub apri il repository e scegli il branch su cui lavorare.
2. **Code → Codespaces → Create codespace on …**
3. Attendi qualche minuto la prima preparazione: il sistema si avvia da solo e si apre in una nuova scheda
   (se non si apre: scheda **Porte** in basso, porta 8000, icona del globo).

Le volte successive riapri lo stesso codespace da **Code → Codespaces**: scarica da solo le ultime modifiche
e riparte. Con un account GitHub personale sono comprese circa 60 ore al mese gratuite; il codespace si sospende
da solo dopo 30 minuti di inattività.

### 2. Sul tuo PC, aggiornandosi da solo

Solo la prima volta: installa [Python](https://www.python.org/downloads/) (su Windows spunta «Add Python to PATH»)
e [Git](https://git-scm.com/downloads), poi scarica il progetto con:

```bash
git clone -b claude/fasas-digital-system-5v69px https://github.com/ambrogiocorti/fasas.git
```

Da quel momento basta **doppio clic su `avvia.bat`** (Windows) o `./avvia.sh` (Mac/Linux): scarica le ultime
modifiche, aggiorna librerie e database, carica i dati demo la prima volta e apre il browser.

### 3. Test automatici

A ogni modifica pubblicata su GitHub i test girano da soli su Linux (SQLite e PostgreSQL) e su Windows:
l'esito è nella scheda **Actions** del repository. In locale: `python manage.py test fasas.tests`.

## Avvio rapido (sviluppo)

Requisiti: Python 3.12+.

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
echo "DJANGO_DEBUG=1" > .env
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

Aprire <http://127.0.0.1:8000> e accedere con uno degli utenti dimostrativi (`admin`, `coordinatore`,
`operatore`, `medico`, `amministrativo`, password `Demo-Fasas-2026!`). I dati demo sono di fantasia.

Senza `DATABASE_URL` viene usato SQLite; per PostgreSQL/Supabase vedere [docs/DEPLOY.md](docs/DEPLOY.md).

## Comandi utili

| Comando | A cosa serve |
|---|---|
| `python manage.py fasas_setup` | ruoli, permessi e configurazioni predefinite (eseguito anche in automatico dopo `migrate`) |
| `python manage.py fasas_genkey` | genera `DJANGO_SECRET_KEY`, `FASAS_ENCRYPTION_KEYS`, `FASAS_BACKUP_KEY` |
| `python manage.py fasas_jobs --list` | elenca i job periodici; `fasas_jobs all` li esegue tutti (escluso il backup) |
| `python manage.py backup_create` / `backup_verify` / `backup_restore FILE --confirm` | backup cifrato, verifica, ripristino |
| `python manage.py audit_verify` | verifica l'integrità della catena di hash dell'audit log |
| `python manage.py supabase_harden` | RLS e revoca dei privilegi ai ruoli API di Supabase (eseguito anche dopo `migrate`) |
| `python manage.py test fasas.tests` | test automatici |

## Struttura

```
config/            impostazioni, URL, Celery
fasas/core         comunità, configurazione, turni, blocco modifiche, cifratura, middleware, job
fasas/accounts     utenti, ruoli, permessi granulari, log accessi
fasas/audit        audit log append-only con catena di hash
fasas/guests       ospiti, tag, contatti, diagnosi, allergie, archiviazione, timeline
fasas/clinical     terapie, somministrazioni, SOS, parametri, eventi, contenzioni, emergenza
fasas/pharmacy     catalogo farmaci, interazioni, lotti, movimenti
fasas/daily        registro, evacuazioni, diario, checklist, turni, chiusura turni
fasas/protocols    regole e motore dei protocolli automatici
fasas/appointments visite e promemoria
fasas/pai          Piano Assistenziale Individuale versionato
fasas/documents    documenti cifrati e versionati
fasas/signatures   firma digitale PAdES e verifica
fasas/notifications notifiche e impostazioni per ruolo
fasas/reports      report PDF/Excel, programmazione, esportazione cartella
fasas/backups      backup cifrati, verifica, ripristino
fasas/search       ricerca globale
fasas/imports      importazione dal FASAS cartaceo (Excel e scansioni)
fasas/offline      modalità senza rete, service worker, foglio di emergenza
fasas/billing      presenze per la rendicontazione, rette, prospetti e incassi
fasas/api          API REST (DRF) per l'app mobile futura
templates/, static/ interfaccia (HTML, CSS, JavaScript senza dipendenze esterne)
```

## Prima della messa in produzione

Il software è completo, ma un sistema che tratta dati sanitari richiede passaggi che non dipendono dal codice:

1. **Validazione clinica dei protocolli**: soglie e azioni predefinite sono esempi; vanno approvate dal medico
   o dal direttore sanitario (campo «validato da» di ogni protocollo). Lo stesso vale per la tabella delle interazioni.
2. **Firma digitale qualificata**: serve il contratto di firma remota di un prestatore qualificato (QTSP) che offra
   le API CSC; la configurazione è descritta in [docs/FIRMA_DIGITALE.md](docs/FIRMA_DIGITALE.md).
3. **GDPR**: registro dei trattamenti, valutazione d'impatto (DPIA, obbligatoria per dati sanitari su larga scala
   o di soggetti vulnerabili), nomina del responsabile del trattamento per hosting e Supabase, informative.
4. **Conservazione a norma**: i report e l'esportazione PDF non sostituiscono la conservazione digitale a norma
   (Linee guida AgID) se richiesta dalla regione o dall'ente: valutare l'invio a un conservatore accreditato.
5. **Requisiti regionali**: struttura e contenuti minimi del FASAS sono definiti dalle normative regionali
   (es. DGR della Lombardia per le strutture sociosanitarie): verificarli con l'ATS/ASL di riferimento.
6. **Chiavi**: conservare `FASAS_ENCRYPTION_KEYS` e `FASAS_BACKUP_KEY` anche fuori dal server (es. cassaforte
   o password manager della direzione). Senza le chiavi documenti e backup non sono recuperabili.
7. **Prova di ripristino**: eseguire periodicamente un ripristino completo su un database di prova.

Dettagli in [docs/SICUREZZA.md](docs/SICUREZZA.md) e [docs/DEPLOY.md](docs/DEPLOY.md).

## Crediti

Le icone dell'interfaccia derivano da [Lucide](https://lucide.dev) (licenza ISC) e sono incluse nel progetto
(`templates/partials/icons.html`): l'applicazione non carica risorse esterne.
