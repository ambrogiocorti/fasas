# Sicurezza, tracciabilità e aspetti legali

## Protezione dei dati

| Misura | Dettaglio |
|---|---|
| Cifratura dei file | Documenti, report e certificati di firma sono cifrati prima di essere scritti (Fernet: AES-128-CBC + HMAC-SHA256). Nomi file casuali, senza dati dell'ospite. Rotazione chiavi: aggiungere la nuova chiave in testa a `FASAS_ENCRYPTION_KEYS`, le vecchie restano per decifrare. |
| Integrità dei file | Ogni versione ha l'impronta SHA-256 del contenuto, verificata a ogni apertura. |
| Accesso ai file | I file non sono mai serviti direttamente: passano da viste autenticate, con permesso e registrazione nell'audit (consultazione / download). |
| Backup | Archivio cifrato AES-256-GCM a blocchi con chiave separata (`FASAS_BACKUP_KEY`); il formato rileva blocchi alterati, riordinati o troncati. Manifest con SHA-256 di ogni componente, verifica automatica dopo ogni backup. |
| Database su Supabase | Dopo ogni `migrate` viene attivata la Row Level Security su tutte le tabelle e revocato ogni privilegio ai ruoli `anon` e `authenticated`: le API REST di Supabase non possono leggere i dati. Connessione con TLS (`DATABASE_SSL_REQUIRE=1`). |
| Trasporto | In produzione: HTTPS obbligatorio, HSTS, cookie `Secure`/`HttpOnly`, `SameSite=Lax`, protezione CSRF, `X-Frame-Options: DENY`, `nosniff`. |
| Dispositivi (senza rete) | Pacchetto del turno e registrazioni in attesa cifrati nel browser con AES-256-GCM; la chiave si apre solo con la password dell'utente (PBKDF2) e si chiude all'uscita e per inattività. Il service worker non memorizza pagine né dati sanitari. Dettagli in [NOTIFICHE_E_SENZA_RETE.md](NOTIFICHE_E_SENZA_RETE.md). |
| Notifiche push ed email | Contenuto push cifrato end-to-end (RFC 8291); per default né push né email contengono nomi o dati sanitari, solo il tipo di avviso. |

## Accessi

- **Rete**: `FASAS_ALLOWED_NETWORKS` limita l'accesso agli indirizzi della comunità (es. rete della struttura o VPN).
- **Password**: minimo 10 caratteri, controlli contro password comuni o simili ai dati utente.
- **Blocco**: dopo `FASAS_LOGIN_MAX_FAILURES` tentativi falliti (default 5) l'utente è bloccato per `FASAS_LOGIN_LOCKOUT_MINUTES`; anche l'endpoint token dell'API applica il blocco.
- **Inattività**: disconnessione automatica dopo i minuti configurati (default 30) – i terminali di reparto sono condivisi.
- **Log accessi**: accesso, uscita, tentativo fallito, blocco, scadenza sessione con IP, user agent e dispositivo. Tabella in sola aggiunta.

## Ruoli e permessi

Ogni ruolo ha il proprio cruscotto e un menu costruito sui suoi permessi: chi non ha un permesso non vede
la voce, il pulsante o la scheda corrispondente, e se apre l'indirizzo a mano riceve un *accesso negato* (403).
Anche le notifiche arrivano solo a chi ha il permesso di vedere ciò a cui rimandano.

| Ruolo | Cruscotto | Cosa fa (spec. §2) |
|---|---|---|
| Operatore | *Il mio turno* | registrazioni giornaliere, farmaci somministrati, eventi, parametri, diario, checklist, chiusura del turno |
| Coordinatore sanitario | *Coordinamento* | gestisce le cartelle ospiti, modifica i protocolli sanitari, valida le informazioni sanitarie (SOS, PAI), autorizza le modifiche oltre la finestra, magazzino, visite, report |
| Medico | *Area medica* | consulta la cartella clinica, prescrive e modifica le terapie, valida gli SOS, registra diagnosi e allergie, firma digitalmente i documenti sanitari |
| Amministratore | *Pannello di sistema* | gestisce utenti e permessi, configura il sistema, i protocolli e le notifiche, controlla audit log e log accessi, gestisce i backup – **non consulta le cartelle cliniche** |
| Amministrativo | *Amministrazione* | ruolo aggiuntivo per l'ufficio amministrativo: presenze per la rendicontazione, rette, prospetti e incassi – vede nome, codice fiscale e giorni di presenza/assenza, **non la cartella clinica** |

| Permesso (esempi) | Operatore | Coordinatore | Medico | Amministratore | Amministrativo |
|---|:-:|:-:|:-:|:-:|:-:|
| Consultare le cartelle degli ospiti | ✔ | ✔ | ✔ | ✖ | ✖ |
| Somministrazioni, parametri, diario, registro, checklist, chiusura turno | ✔ | ✔ | ✖ | ✖ | ✖ |
| Lavorare senza rete sul dispositivo | ✔ | ✔ | ✖ | ✖ | ✖ |
| Registrare eventi clinici | ✔ | ✔ | ✔ | ✖ | ✖ |
| Annullare eventi e registrazioni | ✖ | ✔ | ✖ | ✖ | ✖ |
| Prescrivere / modificare terapie | ✖ | ✔ (trascrizione) | ✔ | ✖ | ✖ |
| Validare farmaci SOS | ✖ | ✔ | ✔ | ✖ | ✖ |
| Modificare dati oltre la finestra di 24 h | ✖ | ✔ | ✔ | ✖ | ✖ |
| Firmare digitalmente | ✖ | ✖ | ✔ | ✖ | ✖ |
| Creare e approvare il PAI | ✖ | ✔ | ✖ | ✖ | ✖ |
| Nuovi ospiti, archiviazione, esportazione, importazione dal cartaceo | ✖ | ✔ | ✖ | ✖ | ✖ |
| Magazzino farmaci, report | ✖ | ✔ | ✖ | ✖ | ✖ |
| Presenze del mese (correzione e chiusura) | ✖ | ✔ | ✖ | ✖ | ✔ |
| Rette, prospetti, incassi | ✖ | ✖ | ✖ | ✖ | ✔ |
| Calendario turni: consultare, chiedere ferie e cambi | ✔ | ✔ | ✖ | ✖ | solo consultazione |
| Calendario turni: pianificare, pubblicare, approvare | ✖ | ✔ | ✖ | ✖ | ✖ |
| Protocolli automatici (regole) | ✖ | ✔ | ✖ | ✔ | ✖ |
| Utenti, configurazione, impostazioni notifiche, audit, log accessi, backup | ✖ | ✖ | ✖ | ✔ | ✖ |

L'amministratore può concedere o negare singoli permessi a singoli utenti (pagina *Utenti → Permessi*), per
esempio dare a un medico l'approvazione del PAI; ogni variazione è nell'audit log. I permessi predefiniti dei ruoli
vengono riallineati a ogni `migrate` (e da `manage.py fasas_setup`); le eccezioni per singolo utente restano.

## Tracciabilità legale

- **Audit log** (`audit_auditlog`): utente, data e ora, azione, oggetto, ospite, valore precedente e nuovo di ogni campo,
  motivazione, IP, origine (web, API, job). Ogni voce contiene l'impronta SHA-256 della precedente.
  - L'applicazione impedisce modifiche e cancellazioni.
  - Su PostgreSQL un trigger rifiuta `UPDATE`, `DELETE` e `TRUNCATE` anche a chi accede direttamente al database.
  - `manage.py audit_verify` (e il job giornaliero) ricalcola la catena: un'alterazione viene individuata e notificata.
- **Annullamento al posto della cancellazione**: le registrazioni cliniche annullate restano visibili (barrate) con motivo, autore e data.
- **Blocco modifiche**: entro la finestra (default 24 h) le correzioni sono libere; oltre, secondo la politica configurata
  (bloccato / con motivazione obbligatoria / solo coordinatore con motivazione).
- **Chiusura turno**: un turno chiuso non accetta inserimenti né modifiche. Chiusura manuale con consegne, o automatica
  dopo la tolleranza configurata. La riapertura straordinaria è disattivata di default; se abilitata è riservata
  all'amministratore, con motivazione tracciata.
- **Cartelle archiviate**: in sola lettura, con data di conservazione.

## Firma digitale

Il sistema produce firme **PAdES** (PDF firmati), verificabili con qualsiasi software di verifica.

- Con un certificato **qualificato** rilasciato da un prestatore iscritto all'elenco di fiducia europeo (QTSP)
  la firma è una Firma Elettronica Qualificata, equivalente alla firma autografa (Reg. UE 910/2014 eIDAS, CAD).
- **Firma remota qualificata** tramite API CSC del prestatore: al prestatore arriva solo l'impronta del documento;
  password, PIN e OTP non vengono salvati. In alternativa certificato personale PKCS#12 (`.p12`/`.pfx`)
  conservato cifrato, con passphrase da inserire a ogni firma.
- Livelli PAdES B-B, B-T (marca temporale RFC 3161), B-LT e B-LTA (`FASAS_SIGNATURE_LEVEL`).
- La verifica sul server controlla integrità, validità crittografica e marca temporale; con le CA dei prestatori in
  `FASAS_SIGNATURE_TRUST_ROOTS` anche la catena di fiducia. Guida completa in [FIRMA_DIGITALE.md](FIRMA_DIGITALE.md).

## GDPR – adempimenti a carico della struttura

I dati trattati sono dati relativi alla salute (art. 9 GDPR) di persone vulnerabili. Oltre alle misure tecniche:

- registro dei trattamenti e informativa agli ospiti / tutori;
- valutazione d'impatto (DPIA);
- nomina a responsabile del trattamento (art. 28) del fornitore di hosting e di Supabase; scelta di una regione UE;
- procedure per la gestione dei data breach (72 ore) e per l'esercizio dei diritti;
- formazione degli operatori e assegnazione di credenziali personali (mai condivise);
- informativa al personale sui log di accessi e operazioni (art. 4 c. 3 L. 300/1970) e designazione degli
  amministratori di sistema.

Bozze di DPIA, registro, informative e nomine in [gdpr/](gdpr/README.md).

## Segnalare un problema di sicurezza

Non aprire issue pubbliche: contattare direttamente il responsabile del progetto.
