# Scale di valutazione, lesioni e medicazioni

Due funzioni nuove della cartella, nella scheda dell'ospite: **Valutazioni** e **Lesioni**. Il FASAS registra ciò
che l'équipe osserva e decide e ricorda le scadenze; non assegna diagnosi, categorie o trattamenti.

## Scale di valutazione

| Scala | A cosa serve | Rivalutazione predefinita |
|---|---|---|
| Indice di Barthel | autonomia nelle attività quotidiane (0–100) | ogni 180 giorni |
| Scala di Braden | rischio di lesioni da pressione (6–23) | ogni 30 giorni |
| Scala di Norton | come la Braden, in alternativa (spenta per default) | ogni 30 giorni |
| Tinetti (POMA) | equilibrio, andatura, rischio di caduta (0–28) | ogni 180 giorni |
| PAINAD | dolore in chi non riesce a comunicarlo (0–10) | al bisogno |
| NRS | dolore riferito dall'ospite (0–10) | al bisogno |

- **Chi**: operatori, coordinatore e medico compilano; coordinatore e medico annullano (con motivo) una valutazione
  sbagliata; il coordinatore sceglie in *Impostazioni › Scale di valutazione in uso* quali scale usare e ogni quanti
  giorni ripeterle (0 = al bisogno).
- **Come**: una domanda per voce con i punteggi della scheda; il FASAS fa la somma e riporta la fascia scritta
  sulla scheda. Le descrizioni delle voci sono brevi: **usare la scheda ufficiale** adottata dalla struttura.
- **Scadenze**: *Clinica › Valutazioni da fare* elenca le scale mai fatte, scadute o in scadenza entro 7 giorni;
  ogni mattina il coordinatore riceve un avviso per quelle scadute.
- **PAI**: la pagina e il PDF del PAI mostrano l'ultima valutazione di ogni scala; la cartella esportata le
  contiene tutte.
- **Diritti d'autore**: alcune scale (es. Braden) sono protette; prima dell'uso verificare che la struttura possa
  usarle (molte strutture lo fanno già sulla carta).

## Lesioni e medicazioni

1. **Nuova lesione** (operatore): sede e lato, tipo, insorgenza (in struttura, già presente all'ingresso, durante
   ricovero), per le lesioni da pressione la **categoria** NPIAP/EPUAP indicata dall'infermiere; misure, fondo e
   foto si possono aggiungere subito. Coordinatore e medico ricevono un avviso.
2. **Piano di medicazione** (coordinatore o medico, come indicato dall'infermiere o dal medico): prodotti,
   modalità, ogni quanti giorni, chi l'ha indicato. Un nuovo piano chiude il precedente, che resta nello storico.
3. **Medicazioni** (operatore): *Turno › Medicazioni da fare* elenca quelle dovute oggi o in ritardo; «Fatta
   adesso» la registra con ora e operatore, «Con note…» per indicare prodotti diversi o osservazioni.
4. **Rivalutazione** (operatore): misure, categoria, fondo, essudato, cute circostante, dolore, segni di infezione,
   foto; di norma ogni 7 giorni (modificabile per ogni lesione).
5. **Chiusura** (coordinatore o medico): «guarita» oppure «chiusa per altro motivo» con nota (es. dimissione); il
   piano termina.

Ogni registrazione ha autore e ora, finisce nell'audit e si annulla con motivo, non si cancella. Le medicazioni e
le rivalutazioni in ritardo arrivano ogni mattina al coordinatore.

### Foto

- Solo con i **dispositivi della struttura** (tablet o PC di reparto), mai con il telefono personale né via chat.
  Sui tablet il campo della foto chiede di aprire la fotocamera (comportamento standard dei browser: provarlo sui
  dispositivi della struttura durante il pilota).
- Inquadrare solo la lesione, se possibile con un righello monouso; niente volto.
- Il FASAS accetta solo JPEG e PNG veri, le riduce a 2000 pixel, toglie posizione GPS e dati del telefono e le
  **cifra** come gli altri documenti (categoria «Foto di lesione»); ogni apertura è registrata.
- Valutare con il DPO l'informativa o il consenso per le foto (DPIA, rischio R18).

## Cosa non fa

- Non calcola la categoria della lesione né sceglie la medicazione: le indica l'équipe.
- Non funziona senza rete: le medicazioni fatte durante un'interruzione si registrano dopo con l'ora reale.
- La somma dei punteggi e la fascia della scala sono un calcolo: con il consulente regolatorio valutare se rientra
  nel regolamento sui dispositivi medici ([DISPOSITIVO_MEDICO.md](DISPOSITIVO_MEDICO.md)).
