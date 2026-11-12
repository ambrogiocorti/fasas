# Presenze per la rendicontazione e rette

Menu **Amministrazione** (ruolo *Amministrativo*; il coordinatore vede e chiude le presenze).

## Presenze

Le presenze di ogni giorno **non si inseriscono a mano**: si ricavano dai movimenti registrati nella cartella
(*Ospite → Ricovero, assenza o rientro*, ingresso e dimissione).

| Codice | Significato |
|---|---|
| P | presente |
| H | assente per ricovero ospedaliero |
| F | assente per rientro in famiglia o assenza programmata |
| A | assente per altro motivo (solo con correzione manuale) |
| – | non in carico (prima dell'ingresso o dopo la dimissione) |

**Regole di conteggio** (*Rette → Regole e intestazione*), da allineare al contratto o alla convenzione con l'ATS:
giorno di ingresso, giorno di dimissione, giorno di uscita e giorno di rientro conteggiati o no come presenza.

Una **correzione** (clic sul giorno nella griglia) prevale sui movimenti e richiede il motivo: serve per i casi
non registrati nella cartella. Ogni correzione è nell'audit log.

**Chiusura del mese**: dopo l'ultimo giorno del mese il coordinatore o l'amministrativo controlla la griglia e la
chiude. Da quel momento le presenze sono «fotografate» e non cambiano più, anche se si registrano movimenti
in ritardo. La riapertura richiede una motivazione ed è possibile solo se non ci sono prospetti già emessi.

**Esportazione**: *Excel* produce la griglia del mese con i totali e la legenda, da usare per la rendicontazione o
da ricopiare nel tracciato richiesto dall'ATS. I flussi regionali hanno formati specifici: vedi la sezione finale.

## Rette

Per ogni ospite una **voce per ciascun pagante**, per esempio:

| Voce | Pagante | €/giorno | Ricovero | Famiglia | Altre assenze |
|---|---|---|---|---|---|
| Quota sanitaria | ATS | 78,50 | 0% | 0% | 0% |
| Quota sociale | Comune | 42,00 | 70% | 70% | 70% |
| Compartecipazione | Famiglia / ADS | 15,00 | 100% | 100% | 100% (max 20 giorni) |

Le percentuali dicono quanto si addebita nei giorni di assenza (es. conservazione del posto); il «massimo giorni di
assenza pagati nel mese» azzera i giorni oltre il limite. Per un **cambio di tariffa** si chiude la voce con la data
di fine e se ne crea una nuova: i prospetti usano per ogni giorno la voce valida in quel giorno.

## Prospetti e incassi

1. Con il mese chiuso: **Genera / aggiorna le bozze** crea un prospetto per ogni ospite e intestatario,
   con le righe *giorni × tariffa × percentuale*.
2. Controllate le bozze e **emettetele**: ricevono un numero progressivo per anno senza salti (es. `2026/0001`)
   e la scadenza secondo i giorni configurati.
3. **PDF** per l'invio all'intestatario (con IBAN e note); **Excel** con l'elenco e le righe per la contabilità.
4. **Registra incasso** (bonifico, SDD, PagoPA, carta, contanti): a saldo il prospetto diventa *Pagato*.
   I prospetti scaduti compaiono nel cruscotto *Amministrazione*.
5. Un prospetto emesso senza incassi si può **annullare** con motivazione e rigenerare.

> I prospetti **non sono fatture elettroniche**. Se la retta va fatturata (fattura elettronica verso privati o
> verso la Pubblica Amministrazione tramite SDI), l'Excel dei prospetti è la base da passare al gestionale di
> fatturazione; l'integrazione diretta con un intermediario SDI è un'evoluzione possibile.

## Da verificare con l'ATS e con il commercialista

- regole di conteggio delle giornate (ingresso, dimissione, uscite) e delle assenze retribuite;
- tracciato e scadenze del **flusso di rendicontazione** regionale delle presenze;
- trattamento fiscale e obbligo di fattura per le diverse quote.
