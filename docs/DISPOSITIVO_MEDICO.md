# FASAS Digitale e il regolamento sui dispositivi medici (MDR 2017/745)

> **Nota preliminare, non un parere legale.** Serve a preparare l'incontro con un consulente regolatorio, che deve
> confermare l'inquadramento prima della vendita. Non dichiara il software dispositivo medico né lo esclude.

## Destinazione d'uso proposta

FASAS Digitale è un **sistema informativo per la tenuta del fascicolo socio-assistenziale e sanitario** di comunità
socio-sanitarie, residenze e centri diurni per persone con disabilità. Serve a **registrare, archiviare, consultare,
trasmettere e stampare** dati inseriti dal personale autorizzato (anagrafica, terapie prescritte dal medico,
somministrazioni, parametri, diario, eventi, PAI, documenti) e a organizzare il lavoro dei turni.

Non formula diagnosi, non calcola dosi, non propone terapie e non sostituisce la valutazione del medico. I promemoria
descritti sotto confrontano dati già registrati dalla struttura secondo regole decise e validate dal medico della
struttura, e sono configurabili.

## Funzioni e domande per il consulente

La guida MDCG 2019-11 valuta un sistema informativo **modulo per modulo**: archiviare, comunicare e cercare dati non
rende un software dispositivo medico; elaborare i dati del singolo paziente per informare decisioni diagnostiche o
terapeutiche può farlo (regola 11, classe IIa o superiore).

| Funzione | Cosa fa con i dati | Stato in FASAS | Domanda per il consulente |
|---|---|---|---|
| Cartella, terapie, giro farmaci, diario, report | registra, archivia, mostra, stampa | sempre attiva | conferma che è fuori dall'MDR |
| Promemoria «stesso farmaco o principio attivo già in terapia» | confronta la nuova prescrizione con le terapie registrate | interruttore in *Configurazione*, acceso | è un semplice controllo di coerenza dei dati o un supporto alla decisione? |
| Promemoria «allergia registrata» | confronta il farmaco con le allergie registrate dalla struttura | interruttore, acceso | come sopra |
| Promemoria interazioni | usa **solo** le regole inserite e **validate dal medico della struttura** (non una banca dati del fornitore) | interruttore, **spento per default** | con regole della struttura il fornitore resta fuori dal perimetro? oppure serve una banca dati con marcatura CE? |
| Protocolli automatici (febbre, glicemia, evacuazioni, crisi, SOS) | avvisa quando un valore registrato supera una soglia | si attivano **solo dopo la validazione del medico**; ogni modifica di soglie o azioni richiede una nuova validazione | soglie della struttura e lista di azioni da spuntare: rientrano nella regola 11? |
| Limiti dei farmaci SOS | blocca una somministrazione oltre il limite scritto nella prescrizione | sempre attiva | è la trascrizione di un limite prescritto o un calcolo? |
| Firma, notifiche, turni, presenze, rette | funzioni organizzative e amministrative | sempre attive | conferma che sono fuori dall'MDR |

## Come si configura

- **Configurazione generale** (amministratore): tre interruttori dei promemoria sulle nuove terapie. Ogni modifica
  finisce nell'audit log.
- **Interazioni farmacologiche**: le inserisce il coordinatore o il medico; entrano nei promemoria solo dopo
  «Valida» del medico. Modificarne una la toglie finché non viene validata di nuovo.
- **Protocolli automatici**: «Valida» del medico; `FASAS_PROTOCOLS_REQUIRE_VALIDATION=0` toglie l'obbligo (sconsigliato).
- Ogni promemoria mostra la frase: *«Promemoria calcolati confrontando i dati registrati dalla struttura (…): non
  sostituiscono la valutazione del medico.»*

## Strade possibili dopo il parere

1. **Fuori dall'MDR** con la destinazione d'uso sopra e le interazioni spente o limitate alle regole della struttura:
   si vende come sistema informativo, con la destinazione d'uso nel contratto e nel manuale.
2. **Interazioni da banca dati certificata**: integrare una banca dati farmaci già marcata CE (servizio a pagamento,
   da scegliere); il modulo resta del fornitore della banca dati.
3. **Marcatura CE di un modulo**: sistema qualità ISO 13485, ciclo di vita IEC 62304, gestione del rischio ISO 14971,
   valutazione clinica e organismo notificato; tempi e costi descritti nell'analisi di prodotto.

Da portare all'incontro: questa pagina, `docs/ARCHITETTURA.md`, l'elenco delle funzioni (README) e una prova del
sistema con i dati di fantasia (`fasas_demo`).
