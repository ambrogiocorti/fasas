# Novità per versione

Il FASAS Digitale segue il [versionamento semantico](https://semver.org/lang/it/): `MAGGIORE.MINORE.CORREZIONE`.
Le versioni 0.x precedono il collaudo in una comunità reale; la 1.0.0 arriverà dopo il pilota.

## Come si rilascia una versione

1. Aggiornare `__version__` in `fasas/__init__.py` e questa pagina.
2. Se cambiano le dipendenze, rigenerare `requirements.lock` (comando in testa al file) e far girare la CI.
3. Commit, poi tag `vX.Y.Z` sul commit con la CI verde.
4. Installare prima nell'ambiente di prova (vedi docs/CONTAINER.md), poi in produzione dopo il collaudo.

## Non ancora rilasciato

### Installazione
- Guida per installare il FASAS su un PC in struttura raggiungibile in HTTPS senza costi, con lista degli oggetti e
  della spesa (docs/INSTALLAZIONE_IN_STRUTTURA.md): Ubuntu Server con disco cifrato sbloccato dal TPM, DuckDNS,
  Backblaze B2 nel piano gratuito, copia mensile su disco USB, calendario di manutenzione e problemi frequenti.
- `scripts/prepara_server.sh`: crea il `.env` con chiavi nuove (mai rigenerate se esiste), aggiorna DuckDNS,
  firewall, aggiornamenti e riavvio automatici, avvio e controllo HTTPS; provato a ogni modifica su Ubuntu 24.04
  nella CI (job «installazione»).
- `scripts/copia_backup_usb.sh`: copia verificata dell'ultimo backup e della busta delle chiavi su disco USB, con
  il registro degli accessi al server e le sue impronte.
- Adempimenti prima dei dati veri (docs/ADEMPIMENTI_PRIMA_DELL_AVVIO.md): chi fa cosa e calendario; modelli di
  nomina dell'amministratore di sistema e di autorizzazione del personale, procedura e registro delle violazioni,
  sicurezza fisica e continuità (docs/SICUREZZA_FISICA_E_CONTINUITA.md); DPIA e registro aggiornati per
  l'installazione in struttura.

### Avvio di prova
- `avvia.sh`/`avvia.bat` controllano che nel database di prova ci siano solo ospiti di fantasia; con le chiavi di
  sviluppo una fascia rossa ricorda in ogni pagina di non inserire dati di persone reali.
- API spenta per default (`FASAS_API_ENABLED`): `/api/v1/` risponde 404 finché non serve a un'app.
- Firma remota qualificata (CSC) nascosta finché non è configurata; firma con CIE mostrata solo se attivata.
- App Android e iOS congelate: la loro compilazione parte solo a mano.

### Somministrazioni e farmaci SOS (stessi controlli da pagina web, API e telefono senza rete)
- Una dose programmata va registrata per un giorno e un orario prescritti, di una terapia attiva, non nel futuro,
  non in un turno chiuso e una sola volta (anche con due registrazioni contemporanee).
- Farmaci SOS oltre il massimo nelle 24 ore o prima dell'intervallo minimo: la struttura sceglie in
  *Configurazione generale* se chiedere una conferma motivata (medico e coordinatore avvisati) o bloccare salvo
  medico e coordinatore. La conferma resta nella somministrazione, nella cartella e nei report.
- Ritorno alla pagina di partenza solo verso indirizzi del FASAS.

### Protocolli
- Soglie e parametri dei protocolli con campi guidati e limiti (niente più testo JSON); ogni modifica richiede di
  nuovo la validazione del medico.
- L'elenco delle azioni è fissato al momento dell'attivazione: si può spuntare solo un'azione prevista e una volta.

### Evacuazioni
- Ogni giorno senza evacuazione è distinto in «verificato: non avvenuta», «non documentato» (nessuna registrazione)
  e «assenza» (ricovero o rientro in famiglia); anche nel protocollo e nel suo riepilogo.

### API
- Token con scadenza (30 giorni per default), rinnovo che revoca il precedente, revoca dal telefono; revoca
  automatica al cambio di password, alla disattivazione dell'utente e allo spegnimento della verifica in due passaggi.

### Report
- Modelli di report: più sezioni, colonne scelte e ordine; PDF, Excel o entrambi; programmazione anche ogni N giorni.

### Scale di valutazione
- Barthel, Braden, Norton (spenta per default), Tinetti, PAINAD e NRS: una domanda per voce con i punteggi della
  scheda, somma e fascia; data della prossima rivalutazione secondo la frequenza scelta dalla struttura.
- Pagina «Valutazioni da fare» e avviso al coordinatore per le valutazioni scadute o mai fatte (ogni mattina).
- Valutazioni più recenti nella pagina e nel PDF del PAI e nella cartella completa esportata. Annullamento con
  motivo, mai cancellazione.

### Correzioni
- Un backup in formato JSON (installazioni con SQLite) su PostgreSQL ora è rifiutato con un messaggio chiaro: prima
  il ripristino si fermava a metà sul blocco dell'audit in sola aggiunta. Test su PostgreSQL di nuovo verdi.

## 0.9.0 – 30/10/2026 (versione per il pilota)

### Sicurezza
- Verifica in due passaggi (codice dall'app sul telefono) obbligatoria per amministratore, coordinatore e medico;
  da fuori rete per tutti, con attivazione solo dalla rete della struttura; codici di recupero; token API con codice.
- Audit log: verifica notturna salvata, punti di controllo con marca temporale RFC 3161 verificabili con OpenSSL,
  rilevamento della storia riscritta; impronta versione 2 indipendente dai numeri interni del database.
- Backup fuori sede su object storage S3 con blocco delle modifiche; prova di ripristino trimestrale con verbale.
- Chiavi di cifratura leggibili da file (credenziali del sistema o segreti del container) e busta di custodia cifrata.

### Affidabilità
- Prova di carico: configurazione dei turni letta una volta per richiesta (era riletta a ogni calcolo: cruscotto
  dell'operatore da 4,5 s a 0,13 s, giro farmaci da 2,1 s a 0,17 s con 60 ospiti); con 20 operatori contemporanei
  il 95% delle pagine risponde in meno di 0,6 s (docs/PRESTAZIONI.md).
- Ripristino dei backup PostgreSQL anche su un server di versione precedente al pg_dump (es. Supabase su 15).
- Controllo di salute `/salute/` con dettaglio protetto da token; job periodici sorvegliati; registro errori
  senza dati sanitari con avviso all'amministratore.
- Dipendenze bloccate con impronte (`requirements.lock`), immagine container e `docker compose` con proxy HTTPS,
  controlli automatici di vulnerabilità (pip-audit) e di sicurezza del codice (bandit) nella CI.
- Backup JSON con orari esatti: l'audit ripristinato resta verificabile (difetto trovato dalla prova di ripristino).

### Conformità
- Bozza dell'accordo art. 28 tra comunità e fornitore (docs/gdpr/ACCORDO_ART28_FORNITORE.md).
- Controlli automatici su interazioni e allergie configurabili, spenti per default in produzione finché non c'è il
  parere sul regolamento dei dispositivi medici; soglie dei protocolli con validazione del medico.
- Firma con CIE: dichiarazione di accettazione delle condizioni della FEA firmata con la CIE prima della prima firma,
  conservata 20 anni; nota informativa e caratteristiche del sistema pubblicabili.

### Funzioni già presenti prima della numerazione
Cartella ospite, terapie e giro farmaci, magazzino, turno e checklist, eventi e contenzioni, protocolli automatici,
PAI, documenti cifrati, firma remota qualificata (CSC) e firma con CIE (FASAS Signer per computer, Android, iPhone),
report, esportazione, lavoro senza rete, notifiche push, presenze e rette, turni del personale, import dal cartaceo.
