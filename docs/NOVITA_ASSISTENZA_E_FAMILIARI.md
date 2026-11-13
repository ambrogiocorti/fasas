# Sei funzioni nuove: attività a orario, cassa degli ospiti, scadenze del personale, indicatori, firma multipla, area familiari

Tutte sono nella stessa base di codice: valgono per l'installazione in struttura, per la versione cloud e per la
presentazione online (dove i dati di esempio le mostrano già compilate). Ognuna è un **modulo** che si spegne e si
riaccende da *Sistema › Moduli*; i dati restano anche a modulo spento.

| Funzione | Chi la usa | Dove | Modulo |
|---|---|---|---|
| Attività a orario per ospite | operatore (spunta), coordinatore (piano) | *Assistenza › Attività del turno*, scheda ospite › **Attività** | Attività a orario |
| Denaro e oggetti personali | operatore, coordinatore, ufficio amministrativo | *Rette, cassa e moduli › Denaro degli ospiti*, scheda ospite › **Denaro e oggetti** | Denaro e oggetti degli ospiti |
| Scadenze del personale | coordinatore, ufficio amministrativo; ognuno le proprie | *Personale › Scadenze del personale*, *Le mie scadenze* | Turni e scadenze del personale |
| Indicatori di qualità | coordinatore, medico | *Archivio e report › Indicatori di qualità* | Report |
| Firma di più documenti | medico (e chi firma) | *Da controllare › Documenti da firmare* | nucleo |
| Area familiari e tutori | familiare, tutore, amministratore di sostegno; coordinatore | *I miei cari* (familiare), *Da controllare › Familiari* (struttura) | Area familiari – **spenta di default** |

## 1. Attività a orario per ospite

Il coordinatore scrive il **piano** nella scheda dell'ospite (*Attività* › *Nuova attività*): riposizionamento,
idratazione, controllo notturno, continenza, mobilizzazione, cura della cute o altro; orari fissi (es. 10:00, 16:00)
oppure «ogni N ore» da un'ora di partenza, eventualmente solo in alcuni turni; istruzioni; dopo quanti minuti è
«in ritardo» (30 di default).

L'operatore trova in *Attività del turno* l'elenco del turno in corso, con quelle in ritardo in evidenza, e spunta
**Fatta** (oppure **Non fatta** o **Rifiutata** con il motivo). Le regole sono quelle delle altre registrazioni:
niente spunte nel futuro, né oltre un'ora prima dell'orario, né in un turno chiuso o su una cartella archiviata;
se un collega ha già spuntato la stessa attività il FASAS lo dice e non crea doppioni; un errore si annulla con
motivo (coordinatore). Ogni 15 minuti un controllo avvisa il coordinatore delle attività rimaste indietro (una sola
volta per orario). Il cruscotto dell'operatore mostra le attività del turno.

## 2. Denaro e oggetti personali degli ospiti

Una **piccola cassa per ospite**: versamenti (dal familiare, dal tutore), spese, contanti consegnati all'ospite,
restituzioni. Le uscite non possono superare il saldo. Lo **scontrino** si fotografa dal telefono o si allega in
PDF: la foto viene ridotta, ripulita dai dati EXIF (posizione) e salvata **cifrata** con la sua impronta; ogni
apertura resta nell'audit. I movimenti non si cancellano: si annullano con motivo (coordinatore, ufficio).

Il **rendiconto PDF** di un periodo (saldo iniziale, entrate, uscite, saldo finale, righe per la firma del
responsabile e del tutore) si scarica dalla pagina dell'ospite. L'inventario degli **oggetti personali** registra
cosa è stato consegnato, da chi, il valore indicativo e lo stato (in struttura, restituito, smarrito, eliminato).

L'ufficio amministrativo vede solo nome, camera e codice fiscale dell'ospite: nessun dato sanitario.

## 3. Scadenze del personale

Corsi e idoneità con la loro periodicità, già proposti alla prima installazione e modificabili (*Tipi e
periodicità*): sicurezza dei lavoratori (5 anni), BLSD (2 anni), antincendio e primo soccorso per gli addetti
designati (5 e 3 anni), preposto (2 anni), HACCP e idoneità alla mansione (data indicata a mano). **Le periodicità
sono proposte: vanno confermate con l'RSPP e il medico competente**, perché dipendono dal livello di rischio e dalle
norme regionali.

Il quadro mostra per ogni dipendente cosa è in regola, in scadenza (60 giorni prima, configurabile), scaduto o
mancante (solo per i ruoli per cui il tipo è obbligatorio); si esporta in CSV. L'attestato si allega cifrato. Per
l'idoneità basta il giudizio consegnato al datore di lavoro: **non si carica la cartella sanitaria e di rischio** e
nelle note non si scrivono diagnosi. Ogni mattina il coordinatore e l'ufficio ricevono il riepilogo, e ciascuno
riceve l'avviso delle proprie scadenze (*Le mie scadenze*).

## 4. Indicatori di qualità nel tempo

Ultimi 12 mesi, mese per mese: cadute, cadute con conseguenze, eventi gravi o critici, nuove lesioni da pressione
**insorte in struttura**, contenzioni avviate, ospiti con contenzione, farmaci SOS dati, ricoveri ospedalieri. Le
frequenze sono **per 1000 giornate di presenza** (dall'ingresso alla dimissione), così si confrontano mesi con un
numero diverso di ospiti; per le contenzioni anche la percentuale di ospiti. Il segnale «in aumento / in calo»
confronta il **mese scorso** (concluso) con la media dei mesi precedenti (soglia ±20%). Contano solo le
registrazioni valide (non annullate). Dati aggregati senza nomi; esportazione CSV per Excel.

## 5. Firma di più documenti in una volta

In *Documenti da firmare* si spuntano i documenti già letti e si preme **Firma i selezionati**: la pagina di
conferma li elenca con il link per aprirli e chiede la conferma «Ho letto i documenti elencati».

- **Certificato (PKCS#12)**: una sola passphrase per tutti, fino a 20 documenti per volta.
- **Firma remota qualificata**: un solo PIN e un solo OTP per tutti, **solo se il prestatore lo consente**
  (`multisign` nelle informazioni della credenziale, letto alla configurazione). Le impronte di tutti i documenti
  vanno insieme nella richiesta di autorizzazione (con SCAL2 sono vincolate all'autorizzazione), poi alla firma.
  Se il prestatore consente una firma per autorizzazione, il FASAS lo dice e si firma un documento alla volta.
- **CIE**: per ora un documento alla volta (ogni firma richiede la carta appoggiata al telefono).

È **tutto o niente**: i PDF si firmano in memoria e si salvano solo se tutte le firme sono riuscite (un PIN
sbagliato non lascia documenti firmati a metà). Ogni documento riceve la propria firma PAdES e una nuova versione;
il livello legale di ciascuna firma è quello dello strumento usato, come per la firma singola.

## 6. Area familiari e tutori (spenta di default)

Vedi [AREA_FAMILIARI_DPO.md](AREA_FAMILIARI_DPO.md) per ciò che il DPO deve valutare **prima** di accenderla.

- Il gestore del sistema crea l'utente con ruolo **Familiare o tutore**; il coordinatore lo **collega** a un ospite
  indicando ruolo (familiare, tutore, amministratore di sostegno, persona indicata dall'ospite) e **base del
  collegamento** (consenso dell'ospite o decreto di nomina), e decide se vede i documenti condivisi e la cassa.
- Il familiare entra e vede **solo** *I miei cari*: la conversazione con la struttura (riservata, una per
  collegamento), le visite (richiesta, conferma o «non possibile» con nota, annullamento), i documenti che il
  coordinatore ha condiviso **uno per uno** (sempre l'ultima versione, ogni apertura nell'audit) e, se previsto,
  saldo e rendiconto della cassa. Qualunque altra pagina del FASAS lo riporta all'area familiari: non vede mai
  cartella, terapie, parametri, diario o eventi.
- La struttura riceve una notifica per ogni messaggio e richiesta di visita (senza il testo del messaggio); il
  familiare riceve le risposte e le decisioni tra le sue notifiche (anche sul telefono, se attivate).
- Il collegamento si revoca con motivo: da quel momento il familiare non vede più l'ospite.
