# Requisiti FASAS, vigilanza e conservazione – checklist per l'incontro con l'ATS/ASL

Il **FASAS** (Fascicolo Socio Assistenziale e Sanitario) è definito dalla normativa regionale sull'esercizio e
l'accreditamento delle unità d'offerta sociosanitarie. Per la **Lombardia** il riferimento principale è la
DGR n. X/2569 del 31 ottobre 2014 e successive modifiche e integrazioni [verificare la versione vigente e le
indicazioni specifiche per la vostra tipologia di unità d'offerta]. Altre regioni hanno strumenti analoghi con
nomi diversi.

## 1. Contenuti del fascicolo – cosa c'è in FASAS Digitale

| Elemento (da confrontare con la DGR vigente) | Dove si trova | Da verificare |
|---|---|---|
| Dati anagrafici, tutela legale, contatti | Cartella → anagrafica e contatti | [ ] |
| Documentazione di ingresso, consensi, documenti d'identità | Documenti (cifrati, versionati) | [ ] |
| Valutazione multidimensionale / scale di valutazione | Documenti; [eventuale modulo dedicato da sviluppare] | [ ] |
| Progetto individuale e PAI con verifiche | PAI per aree, versioni, PDF firmabile | [ ] |
| Diario degli interventi (sanitario, assistenziale, educativo) | Diario, registro giornaliero, eventi | [ ] |
| Terapie, somministrazioni, farmaci al bisogno | Terapie, giro farmaci, SOS con validazione | [ ] |
| Parametri, eventi, cadute, contenzioni con prescrizione e monitoraggio | Parametri, eventi, contenzioni | [ ] |
| Visite e referti | Appuntamenti, documenti | [ ] |
| Dimissione e trasferimento | Dimissione con archiviazione; esportazione completa in PDF | [ ] |

## 2. Requisiti di tenuta – domande da porre

- [ ] Ogni registrazione deve riportare **autore, data e ora**: FASAS lo fa per ogni voce e conserva lo storico nell'audit log. È sufficiente l'identificazione tramite credenziali personali, o serve la **firma digitale** su alcuni documenti (PAI, prescrizioni, contenzioni)?
- [ ] **Correzioni**: le registrazioni non si cancellano ma si annullano con motivo; dopo 24 ore le modifiche richiedono motivazione. È conforme alle indicazioni?
- [ ] **Accesso degli ispettori** in sede di vigilanza: consultazione a video con un operatore, esportazione PDF della cartella, oppure un'utenza temporanea in sola lettura? [Un'utenza di sola lettura si crea con i permessi granulari.]
- [ ] **Coesistenza carta/digitale** nel periodo di passaggio e valore delle scansioni dello storico.
- [ ] Il FASAS può essere **interamente digitale**? Con quali condizioni?
- [ ] Tracciato e scadenze del **flusso di rendicontazione** delle presenze; regole su giornate di ingresso, dimissione e assenze.
- [ ] Tempi di **conservazione** del fascicolo dopo la dimissione.

## 3. Dematerializzazione e conservazione a norma

Se il fascicolo diventa solo digitale, i documenti informatici vanno formati e conservati secondo il **Codice
dell'amministrazione digitale** (D.Lgs. 82/2005, art. 44) e le **Linee guida AgID sulla formazione, gestione e
conservazione dei documenti informatici** (in vigore dal 1° gennaio 2022).

| Punto | Stato in FASAS Digitale | Cosa serve |
|---|---|---|
| Formazione del documento con autore, data e integrità | ✔ audit log con catena di hash; PDF con firma PAdES e marca temporale | – |
| Formati idonei alla conservazione (PDF/A, XML) | PDF generati dal sistema; [verificare PDF/A] | eventuale adeguamento a PDF/A |
| Pacchetti di versamento con metadati | ✖ | invio periodico (es. alla dimissione) a un **conservatore** accreditato/qualificato: integrazione da sviluppare una volta scelto il conservatore |
| Manuale di conservazione e responsabile della conservazione | ✖ (organizzativo) | nomina e manuale, anche tramite il conservatore |
| Distruzione della carta dopo la scansione | – | solo dopo verifica con ATS e secondo le regole sulla copia per immagine conforme |

Finché questi punti non sono definiti, **il cartaceo chiuso resta l'originale da conservare** e FASAS Digitale è il
sistema di lavoro quotidiano con esportazioni PDF periodiche archiviate.

## 4. Riepilogo per l'incontro

Portare: questa checklist, una dimostrazione del sistema con dati di prova, l'esportazione PDF di una cartella
di prova, la DPIA in bozza. Annotare le risposte e aggiornare la configurazione (blocco modifiche, regole delle
presenze, conservazione) e la roadmap.
