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

## Accessi

- **Rete**: `FASAS_ALLOWED_NETWORKS` limita l'accesso agli indirizzi della comunità (es. rete della struttura o VPN).
- **Password**: minimo 10 caratteri, controlli contro password comuni o simili ai dati utente.
- **Blocco**: dopo `FASAS_LOGIN_MAX_FAILURES` tentativi falliti (default 5) l'utente è bloccato per `FASAS_LOGIN_LOCKOUT_MINUTES`; anche l'endpoint token dell'API applica il blocco.
- **Inattività**: disconnessione automatica dopo i minuti configurati (default 30) – i terminali di reparto sono condivisi.
- **Log accessi**: accesso, uscita, tentativo fallito, blocco, scadenza sessione con IP, user agent e dispositivo. Tabella in sola aggiunta.

## Ruoli e permessi

| Permesso (esempi) | Operatore | Coordinatore | Medico | Amministratore |
|---|:-:|:-:|:-:|:-:|
| Registrare somministrazioni, parametri, eventi, diario, registro | ✔ | ✔ | parziale | ✔ |
| Annullare eventi e registrazioni | ✖ | ✔ | ✖ | ✔ |
| Prescrivere / modificare terapie | ✖ | ✔ (trascrizione) | ✔ | ✖ |
| Validare farmaci SOS | ✖ | ✔ | ✔ | ✖ |
| Modificare dati oltre la finestra di 24 h | ✖ | ✔ | ✔ | ✔ |
| Firmare digitalmente | ✖ | ✖ | ✔ | ✖ |
| Approvare il PAI | ✖ | ✔ | ✔ | ✖ |
| Archiviare ospiti, esportare la cartella | ✖ | ✔ | ✖ | ✔ |
| Utenti, configurazione, notifiche, audit, backup | ✖ | ✖ | ✖ | ✔ |

L'amministratore può concedere o negare singoli permessi a singoli utenti (pagina *Utenti → Permessi*);
ogni variazione è nell'audit log. L'amministratore di sistema, per scelta, non prescrive, non firma e non valida atti clinici.

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
- Modalità supportata subito: certificato personale PKCS#12 (`.p12`/`.pfx`), conservato cifrato; la passphrase
  non viene salvata e va inserita a ogni firma. Marca temporale opzionale con `FASAS_SIGNATURE_TSA_URL`.
- Firma remota con OTP: `RemoteQTSPProvider` in `fasas/signatures/providers.py` è il punto in cui collegare le API
  del provider scelto (Aruba, InfoCert, Namirial…), una volta stipulato il contratto.
- La verifica sul server controlla integrità e validità crittografica; l'attendibilità del certificato va confermata
  con un software che usi la lista di fiducia europea.

## GDPR – adempimenti a carico della struttura

I dati trattati sono dati relativi alla salute (art. 9 GDPR) di persone vulnerabili. Oltre alle misure tecniche:

- registro dei trattamenti e informativa agli ospiti / tutori;
- valutazione d'impatto (DPIA);
- nomina a responsabile del trattamento (art. 28) del fornitore di hosting e di Supabase; scelta di una regione UE;
- procedure per la gestione dei data breach (72 ore) e per l'esercizio dei diritti;
- formazione degli operatori e assegnazione di credenziali personali (mai condivise).

## Segnalare un problema di sicurezza

Non aprire issue pubbliche: contattare direttamente il responsabile del progetto.
