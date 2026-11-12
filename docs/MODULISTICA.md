# Modulistica: moduli online e su carta

Informative, autorizzazioni, consensi, accordi e richieste si gestiscono nel FASAS, in *Sistema › Modulistica*.
Ogni modulo si può **compilare online** oppure **stampare** (vuoto o già compilato) e firmare su carta. I testi
predefiniti sono sintetici e vanno adattati alla struttura con il DPO: non sono un parere legale.

## Chi fa cosa

| Ruolo | Cosa fa con i moduli |
|---|---|
| **Amministratore** (di sistema) | completa l'**intestazione** (titolare, sede, recapiti, DPO); modifica testi e campi; crea moduli nuovi; li **pubblica** o archivia; li **distribuisce** al personale e vede chi li ha compilati. Non vede i moduli compilati dagli ospiti, solo quanti sono |
| **Coordinatore** e **ufficio amministrativo** | compilano con l'ospite o il suo rappresentante i moduli degli ospiti, stampano i vuoti, caricano la scansione dei moduli firmati, registrano le revoche dei consensi |
| **Ogni utente del personale** | trova in *I miei moduli* ciò che deve leggere e confermare (informativa, autorizzazione) e ne scarica la copia |
| **Familiare** (se l'area familiari è accesa) | compila online i moduli destinati ai familiari dall'area *I miei cari* |

### Amministratore e amministrativo: la differenza

- L'**amministratore** è il responsabile tecnico e organizzativo del sistema (l'«amministratore di sistema»):
  utenti e permessi, configurazione, moduli accesi o spenti, notifiche, backup, audit, modulistica. Non consulta le
  cartelle degli ospiti e non compie atti clinici. Riceve una designazione scritta e il suo operato si verifica
  ogni anno.
- L'**amministrativo** è l'ufficio amministrativo della comunità: presenze per la rendicontazione, rette,
  prospetti e incassi, cassa e oggetti degli ospiti, scadenze del personale, moduli degli ospiti (per esempio
  l'accordo per la cassa). Vede l'anagrafica essenziale degli ospiti, non la cartella clinica, e non configura il
  sistema.

## Come funziona

1. **Intestazione** (*Modulistica › Intestazione*): una volta sola. Riempie le variabili `{titolare}`, `{sede}`,
   `{contatti}`, `{dpo}`, `{contatti_dpo}` in tutti i moduli.
2. **Testi e campi**: ogni modulo ha un testo (paragrafi, elenchi con «- », **grassetto**) e dei campi: testo breve
   o lungo, data, una o più scelte, dichiarazione da spuntare, sottotitolo. Nei moduli del personale `{utente}` e
   `{ruolo}`, in quelli degli ospiti `{ospite}` diventano i nomi veri. *Anteprima online* e *PDF da stampare*
   mostrano il risultato prima di pubblicare.
3. **Versioni**: se un modulo già compilato viene modificato, nasce una nuova versione. Le compilazioni precedenti
   restano con il testo di allora (si conserva una «fotografia» del modulo e delle risposte).
4. **Destinatari**: ospiti (compilato in struttura), familiari (online), personale (per ruolo). Con «chiedere
   anche ai nuovi utenti» i nuovi assunti lo trovano subito tra i loro moduli.
5. **Distribuzione al personale**: *Distribuisci* sceglie i ruoli e, se serve, una scadenza; ognuno riceve una
   notifica. La tabella mostra chi ha compilato e chi no.

## Online o su carta

- **Online**: risponde l'ospite o il suo rappresentante (in struttura, con il coordinatore o l'ufficio), il
  dipendente (*I miei moduli*) o il familiare (*I miei cari*). Il FASAS registra **chi ha risposto, quando, con
  quale utente e da quale indirizzo**, salva il PDF cifrato e, per gli ospiti, lo mette nei *Documenti* (categoria
  «Modulo»).
- **Su carta**: *Stampa vuoto* dà il PDF da compilare a mano; il modulo compilato online si stampa già compilato.
- **Firma**: la conferma online **non è una firma**. I moduli marcati «richiede la firma» (accordo per la cassa,
  consenso alle foto, richiesta di accesso per i familiari, designazione dell'amministratore di sistema) restano
  «da firmare» finché non si carica la **scansione del foglio firmato a mano** (o non si firma il PDF
  digitalmente dai documenti dell'ospite, con gli strumenti di firma già previsti dal FASAS). *Moduli degli
  ospiti* elenca quelli in attesa di firma. Per le informative e le autorizzazioni la struttura può decidere, con
  il DPO, se basta la conferma online o se richiedere la firma: è un'opzione del modulo.
- **Revoca**: i consensi (per esempio le foto delle lesioni) si revocano con il motivo; resta tutto nello storico.

## Moduli predefiniti

| Modulo | Per | Firma |
|---|---|---|
| Informativa sul trattamento dei dati – ospiti | ospiti, familiari | conferma online (spazio firma sul cartaceo) |
| Informativa al personale sull'uso del FASAS | personale (tutti i ruoli) | conferma online |
| Autorizzazione al trattamento dei dati e istruzioni | personale | conferma online |
| Designazione ad amministratore di sistema | amministratore | firma |
| Accordo per la piccola cassa e gli oggetti personali | ospiti | firma |
| Fotografie delle lesioni – informazione e consenso | ospiti | firma, revocabile |
| Richiesta di esercizio dei diritti | ospiti, familiari, personale | conferma online (spazio firma sul cartaceo) |
| Informativa per gli utenti dell'area familiari | familiari | conferma online |
| Richiesta di accesso all'area familiari | ospiti (in struttura) | firma |

*Ripristina il testo predefinito* riporta un modulo al testo originale (crea una nuova versione se era già stato
compilato). Il pacchetto cartaceo con tutti i PDF dei moduli predefiniti e i documenti di governo (registro, DPIA,
nomine, procedure) si genera con `python scripts/genera_pacchetto_privacy.py`.
