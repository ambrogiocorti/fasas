# Novità per versione

Il FASAS Digitale segue il [versionamento semantico](https://semver.org/lang/it/): `MAGGIORE.MINORE.CORREZIONE`.
Le versioni 0.x precedono il collaudo in una comunità reale; la 1.0.0 arriverà dopo il pilota.

## Come si rilascia una versione

1. Aggiornare `__version__` in `fasas/__init__.py` e questa pagina.
2. Se cambiano le dipendenze, rigenerare `requirements.lock` (comando in testa al file) e far girare la CI.
3. Commit, poi tag `vX.Y.Z` sul commit con la CI verde.
4. Installare prima nell'ambiente di prova (vedi docs/CONTAINER.md), poi in produzione dopo il collaudo.

## Non ancora rilasciato

Nuova modalità d'installazione e sei funzioni nuove (spente nella «configurazione per il pilota», l'area
familiari spenta di default ovunque).

### Assistenza, amministrazione, personale, familiari (docs/NOVITA_ASSISTENZA_E_FAMILIARI.md)
- **Attività a orario per ospite**: piano (orari fissi o «ogni N ore», per turno), elenco del turno con spunta,
  regole delle registrazioni (niente doppioni, turni chiusi, annullamento con motivo), avviso al coordinatore
  delle attività in ritardo ogni 15 minuti, riquadro nel cruscotto dell'operatore.
- **Denaro e oggetti personali**: piccola cassa per ospite con saldo che non va sotto zero, scontrino fotografato
  (ridotto, senza EXIF, cifrato), annullamento con motivo, rendiconto PDF per il tutore, inventario degli oggetti;
  l'ufficio amministrativo non vede dati sanitari.
- **Scadenze del personale**: tipi proposti (sicurezza, BLSD, antincendio, primo soccorso, preposto, HACCP,
  idoneità) con periodicità modificabili, quadro per dipendente, attestati cifrati, CSV, avvisi giornalieri al
  coordinatore, all'ufficio e al diretto interessato («Le mie scadenze»).
- **Indicatori di qualità**: 12 mesi di cadute, cadute con conseguenze, eventi gravi, nuove lesioni da pressione,
  contenzioni, SOS e ricoveri per 1000 giornate di presenza, confronto con la media, CSV.
- **Firma di più documenti in una volta**: una passphrase (certificato) o un solo PIN e OTP (firma remota in
  lotto con le impronte vincolate all'autorizzazione, se il prestatore lo consente); tutto o niente.
- **Area familiari e tutori** (spenta di default, da accendere dopo il parere del DPO – docs/AREA_FAMILIARI_DPO.md):
  ruolo «Familiare o tutore», collegamenti con base giuridica, messaggi, visite, documenti condivisi uno per uno,
  cassa per il tutore; il familiare non può aprire nessun'altra pagina del FASAS.
- **Modulistica** (docs/MODULISTICA.md): informative, autorizzazioni, consensi, accordi e richieste modificabili
  dall'amministratore (intestazione, testi, campi, versioni, pubblicazione), distribuiti al personale per ruolo e
  ai nuovi utenti, compilabili online (personale, ospiti in struttura, familiari) o stampabili vuoti e compilati;
  i moduli da firmare restano «da firmare» fino alla scansione del foglio firmato; revoca dei consensi; nove
  moduli predefiniti sintetici, gli stessi stampati nel pacchetto `scripts/genera_pacchetto_privacy.py`.
- Presentazione e prova locale: dati di esempio per tutte le novità, utente `familiare`, certificato di prova
  (firma non qualificata) per il medico della demo.

### Versione cloud (docs/CLOUD.md)
- **Il FASAS su un dominio senza server in struttura**: un container (`FASAS_CLOUD=1`) con sito e pianificatore dei
  job, porta `$PORT`, file statici serviti dal FASAS (WhiteNoise), dominio da `FASAS_DOMAIN`; `render.yaml` pronto
  per Render (piano gratuito, pubblicazione manuale dopo il collaudo).
- **Supabase**: migrazioni SQL in `supabase/migrations` (schema, dati iniziali, protezione dalle API: RLS su ogni
  tabella e nessun privilegio ad `anon`, `authenticated`, `service_role`), generate da
  `scripts/genera_migrazioni_supabase.py` e provate nella CI con l'immagine ufficiale del PostgreSQL di Supabase.
- **File cifrati su Supabase Storage** (S3): indirizzi «path», niente intestazioni non supportate; il controllo di
  salute verifica lo storage.
- **Pianificatore integrato** (`manage.py fasas_pianificatore`) al posto di Celery e Redis: stessi orari (ora
  un'unica tabella anche per Celery), recupero dei job saltati mentre il servizio era fermo, una sola esecuzione
  anche con più copie attive, cambi dell'ora legale senza backup persi o doppi.
- **Backup** con i file dell'object storage e ripristino che li rimette al loro posto; su Supabase `pg_dump` del solo
  schema `public` e ripristino che non tocca lo schema; copia fuori sede anche su un bucket Supabase.
- **Primo amministratore** da `FASAS_ADMIN_USERNAME` e `FASAS_ADMIN_PASSWORD` se non ce n'è nessuno.
- Controlli all'avvio che fermano un servizio senza storage dei file, dominio o chiavi; `/salute/` risponde ai
  controlli interni del servizio di hosting con qualsiasi Host.

### Presentazione online (docs/PRESENTAZIONE.md)
- **`FASAS_PRESENTAZIONE=1`**: il FASAS online per mostrarlo, senza nulla da configurare. Database SQLite nel container
  con lo schema già pronto nell'immagine, dati di esempio ricreati a ogni avvio con le date di oggi, chiavi pubbliche
  di prova, utenti di prova senza verifica in due passaggi, niente backup; fascia rossa in ogni pagina.
- `render.yaml` è ora la presentazione (Render › Blueprint › Apply, piano Free, domini fasas.online e www); la
  versione cloud per i dati veri è in `deploy/render-cloud.yaml`.
- Password riservata facoltativa (`FASAS_PRESENTAZIONE_PASSWORD`); prova dell'immagine in modalità presentazione nella CI.
- Senza carta di credito: `scripts/presentazione_pythonanywhere.sh` installa la presentazione su un account gratuito di
  PythonAnywhere (server UE) con un solo comando, scrive il file WSGI e rigenera i dati di esempio a richiesta.

### fasas.online (docs/FASAS_ONLINE.md)
- **Database dedicato obbligatorio**: con tabelle di altre applicazioni nello schema (per esempio un progetto
  Supabase già usato da un'altra app) il FASAS non parte (`fasas.E107`) e non crea nulla; la protezione dalle API
  agisce solo su tabelle, sequenze e funzioni del FASAS; il primo file SQL si ferma se lo schema non è vuoto.
- **Dominio unico**: nella versione cloud `www` e il nome tecnico dell'hosting rimandano al primo nome di
  `FASAS_DOMAIN` (dal repository `fasas-deploy`, ora integrato qui); Caddy rimanda gli altri nomi
  (`FASAS_DOMAIN_ALIASES`).
- **`prepara_server.sh --vps`**: server affittato su internet, senza rete della struttura né DuckDNS; controllo che il
  DNS punti al server; SSH aperto con limite ai tentativi; provato a ogni modifica nella CI.
- **Pubblicazione controllata**: workflow «Pubblica su fasas.online» (solo commit con la CI verde, ambiente con
  approvazione); `aggiorna_fasas.sh --versione` con backup prima e **ritorno automatico** a codice e immagine di
  prima se la nuova versione non risponde (provato nella CI con una versione volutamente rotta).
- `scripts/avvia_cloud.sh` per gli hosting Python senza Docker.
- Test dei casi critici che mancavano: terapia modificata senza permessi, terapia sospesa mentre il telefono è senza
  rete, operatore disattivato che sincronizza, invio ripetuto dopo un riavvio.

## 0.10.0 – 04/11/2026 – versione per il pilota

Da questa versione si fanno solo correzioni fino alla fine del pilota (docs/PIANO_PILOTA.md).

### Pilota
- **Moduli accendibili** (Configurazione › Moduli): PAI, valutazioni, lesioni, protocolli automatici, appuntamenti,
  magazzino, importazione, turni, presenze e rette, report, segnalazioni e firma remota si spengono uno per uno
  (menu, cruscotti, pagine, promemoria e job) senza perdere dati; «Applica la configurazione per il pilota».
- **Segnala un problema** in ogni pagina (solo percorso e ora, niente parametri né dati degli ospiti); elenco con
  stato e risposta per l'amministratore, notifica, CSV.
- **Indicatori del pilota**: dosi registrate, mancanti e in ritardo salvate a ogni chiusura turno, durata del giro
  farmaci, checklist, segnalazioni; CSV per il confronto con il cartaceo. Piano del pilota in docs/PIANO_PILOTA.md.
- **Pacchetto per l'ispezione**: un PDF per la vigilanza ATS/ASL con ospiti e PAI, somministrazioni, eventi,
  contenzioni, scadenze, protocolli, backup e verifica del registro delle operazioni.

### Farmaci
- **Elenco ufficiale dei medicinali** (open data AIFA, CC BY 4.0): caricamento di CSV o Excel con le colonne
  riconosciute dal nome (provato con file costruiti sul formato atteso: il file AIFA va provato al primo
  caricamento), ricerca, compilazione della scheda del farmaco; codice AIC di 9 cifre.
- **Controllo della confezione** nel giro farmaci con lettore di codici a barre o fotocamera (dove il browser legge
  i codici): evidenzia le dosi del turno con quel farmaco; non registra e non blocca.

### Firma e app
- **App Android dal FASAS**: Sistema › Pubblica l'app (APK letto e controllato dal FASAS), Impostazioni › App per il
  telefono con QR code, avviso di aggiornamento nell'app; APK definitivo firmato con la chiave della struttura nella
  CI se ci sono i segreti (docs/FIRMA_CIE.md, «Distribuire l'app»).
- **Firma con il PIN della carta solo dopo il collaudo**: firma dei documenti, accettazione della FEA e verifica con
  il PIN della carta restano spente finché in struttura non riesce una firma di prova con una CIE vera. La verifica
  con CIE + PIN FASAS non cambia.

### Accessibilità e continuità
- Controllo automatico di accessibilità (axe-core, WCAG 2.1 A e AA) di 65 pagine per tutti i ruoli, in chiaro e in
  scuro, nella CI; corretti link riconoscibili solo dal colore e un campo senza nome. Testo più grande per utente
  (Il mio profilo).
- docs/SECONDO_TECNICO.md (guida per chi sostituisce lo sviluppatore) e docs/MODELLO_CONTRATTO_ASSISTENZA.md.


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

### Lesioni e medicazioni
- Nuova scheda «Lesioni» nella cartella: sede, tipo, insorgenza, categoria NPIAP/EPUAP delle lesioni da pressione,
  rilevazioni con misure, fondo, essudato, cute circostante, dolore, segni di infezione e foto.
- Foto solo JPEG/PNG verificate, ridotte, senza posizione GPS e cifrate come i documenti.
- Piano di medicazione indicato da infermiere o medico; pagina «Medicazioni da fare» con «Fatta adesso»; avvisi
  per nuove lesioni (coordinatore e medico) e per medicazioni o rivalutazioni in ritardo (coordinatore).
- Lesioni aperte nel PAI (pagina e PDF) e storico completo nella cartella esportata. Guida:
  docs/VALUTAZIONI_E_LESIONI.md.

### Test e documentazione
- Test delle schermate di uso quotidiano e di amministrazione: viste coperte dal 66% al 91% (quelle del turno sopra
  l'83%); test dei comandi `backup_create`, `backup_verify` e `backup_restore` con ripristino completo.
- `backup_restore` segnala con un messaggio chiaro un file inesistente.
- Schede di una pagina per operatore, coordinatore, medico e amministrativo (docs/guide/).
- README senza sezioni ripetute; una sola guida d'installazione (in struttura, con Docker); Supabase fuori dal
  percorso principale (`.env.example` e docs/DEPLOY.md); roadmap aggiornata con Backblaze B2 e le nuove funzioni.

### Continuità
- Disco di continuità: un SSD esterno sempre collegato riceve ogni 5 minuti una copia cifrata del database e i file
  nuovi; con un guasto del server si perdono al massimo pochi minuti di registrazioni. Se il disco manca la copia
  si ferma senza scrivere sul disco interno, l'amministratore riceve un avviso e `/salute/` lo segnala.
  Preparazione con `scripts/disco_continuita.sh` (provato nella CI con un disco virtuale), ripristino con
  `manage.py fasas_ripristina_continuita`.
- Guida: FASAS raggiungibile in struttura anche senza linea internet (DNS locale del router, passo 7b) e prova
  semestrale del gruppo di continuità e del lavoro senza rete.
- Piano di continuità per l'ATS (docs/PIANO_DI_CONTINUITA.md): chi fa cosa per ogni tipo di interruzione,
  ritorno alla normalità, prove e registro delle interruzioni.

### Accesso da fuori struttura per utente
- Nuova impostazione dell'utente «Può entrare da fuori struttura»: se tolta, il FASAS si apre solo dalla rete
  della struttura (tablet e PC di reparto, senza codice sul telefono); da fuori l'accesso è rifiutato, una
  sessione che passa dal Wi-Fi ai dati mobili si chiude e l'API non accetta token. Alternativa semplice alla VPN
  per chi non usa il FASAS da casa.

### Corrente e foglio di emergenza
- Gruppo di continuità con NUT (`scripts/gruppo_continuita.sh`): quando manca la corrente il FASAS avvisa
  operatori, coordinatori e amministratori (anche sul telefono); sotto il 40% di batteria (o 3 minuti di
  autonomia) ferma il FASAS in modo ordinato e spegne il server, che riparte da solo al ritorno della corrente.
  Stato nel controllo di salute. Provato nella CI con un gruppo simulato; con il gruppo vero va fatta la prova
  del passo 15b.
- Database e servizi con tempi di arresto adeguati (60 e 30 secondi) per chiudersi in modo ordinato.
- Riapertura dei turni per trascrivere il foglio di emergenza: ora la fa il coordinatore, con la motivazione
  proposta; il turno riaperto si richiude da solo dopo 12 ore. Abilitata per default (la direzione può
  disattivarla).

### Menu e CIE
- Menu laterale a tendine raggruppate per attività (Assistenza, Turno, Da controllare, Clinica, Personale, Archivio
  e report, Amministrazione, Sistema): aperta quella della pagina corrente, conteggi visibili anche a tendina chiusa.
- Verifica con CIE per aprire, scaricare o modificare i documenti, anche firmati (Configurazione generale, spenta
  per default): la carta firma una sfida casuale, il certificato deve essere della CIE e intestato all'utente;
  accesso a quel documento per pochi minuti, nell'audit. Vale anche per l'esportazione della cartella con i
  documenti. Chi non firma può abbinare il telefono solo per verificarsi (docs/FIRMA_CIE.md, sezione 8b).
- **CIE senza il suo PIN**: per aprire i documenti si appoggia la CIE al telefono e si digita il **PIN FASAS**
  scelto al primo accesso (predefinito in Configurazione generale; chi ricorda il PIN della carta può usare anche
  quello). Protocollo NIS del Ministero: SOD verificato con la CSCA italiana e autenticazione interna della carta su
  una sfida del server; registrazione confermata di persona da un amministratore; PIN FASAS solo come impronta,
  bloccato dopo 5 errori. Firmare con la CIE richiede ancora il PIN della carta.
- App Android FASAS Signer 0.2: aspetto della piattaforma (colori, icone, schede, tema chiaro e scuro, icona
  dell'app), riquadro di stato con i passi della lettura, dialoghi con il codice di controllo in evidenza, PIN e
  esiti chiari, «Scollega questo telefono». Schermate controllate senza telefono con Paparazzi nella CI.
- Logo FASAS (fascicolo con il tracciato del battito) in favicon, web app installata, iPhone, notifiche, menu e
  pagina di accesso; l'app FASAS Signer ha la stessa icona con il segno «appoggia la carta», anche monocromatica.
  Tutto generato da `scripts/genera_icone.py`.
- Modalità senza rete anche per il medico, in **sola lettura** (terapie, allergie, contatti): nessuna registrazione.
- CIE già registrata e registrata di nuovo dallo stesso utente (es. app reinstallata): restano PIN FASAS e conferma;
  messaggio più chiaro se la carta è registrata per un altro utente. Nell'app, il dialogo del PIN della carta
  ricorda che non è il PIN FASAS e di annullare invece di tirare a indovinare.
- App Android: la lettura della CIE resta attiva fino all'esito (prima poteva restare ferma su «Avvicina la CIE»),
  messaggi a ogni passo, carta spostata = si riappoggia e si riprende; «Prova la lettura della CIE» senza FASAS
  (anche del PIN, con il codice fiscale letto dalla carta) e spiegazione di dove trovare il PIN.

### Manutenzione del server
- `scripts/aggiorna_fasas.sh`: la manutenzione del mese in un comando. `--controlla` dice se gli aggiornamenti
  automatici di Ubuntu funzionano, se serve un riavvio, se c'è una nuova versione e quanto sono vecchi i
  contenitori; senza opzioni fa un backup verificato, aggiorna versione e contenitori, riavvia il FASAS e controlla
  che risponda. Riavvio del server solo con `--riavvia` e mai se il disco chiederebbe la frase alla tastiera.
  Registro in `/var/log/fasas-aggiornamenti.log`.
- `scripts/accesso_remoto.sh`: VPN WireGuard di manutenzione per l'amministratore (gratuita, senza servizi
  esterni): SSH da casa senza aprire la porta 22, un accesso per PC con ultimo collegamento, revoca immediata.
  Provata nella CI con un «PC di casa» simulato in una rete separata (passo 15c della guida).

### Correzioni
- Evacuazioni: un «non avvenuta» registrato dopo mezzanotte ora vale per il giorno appena iniziato (prima veniva
  attribuito alla notte del giorno precedente e il conteggio dei giorni non documentati sbagliava di uno).
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
