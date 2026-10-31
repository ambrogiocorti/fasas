# Accordo sul trattamento dei dati (art. 28 GDPR) tra la comunità e il fornitore del FASAS – bozza

> **Bozza di lavoro, non un contratto pronto.** Va completata e rivista dal legale/DPO della comunità e del fornitore
> prima della firma. Le parti tra parentesi quadre vanno compilate. Riguarda il caso in cui il fornitore gestisce il
> FASAS in abbonamento (servizio ospitato); se la comunità installa il FASAS sui propri server e il fornitore fa solo
> assistenza, si usa la stessa struttura limitata all'assistenza.

## 1. Parti e ruoli

- **Titolare del trattamento**: [ragione sociale della comunità], [sede], [codice fiscale/P. IVA], in persona di
  [legale rappresentante].
- **Responsabile del trattamento**: [ragione sociale del fornitore], [sede], [codice fiscale/P. IVA].
- Il responsabile tratta i dati solo per erogare il servizio FASAS Digitale descritto nel contratto principale e
  solo su istruzione documentata del titolare (questo accordo, il contratto, le richieste scritte).

## 2. Oggetto del trattamento

| Elemento | Contenuto |
|---|---|
| Natura e finalità | ospitare, mantenere, aggiornare e mettere in sicurezza il FASAS; backup e ripristino; assistenza su richiesta |
| Interessati | ospiti della comunità, loro familiari e tutori, personale, medici |
| Categorie di dati | dati identificativi e di contatto; **dati relativi alla salute** (art. 9): diagnosi, terapie, parametri, eventi, documenti sanitari; dati di accesso e di audit del personale |
| Durata | durata del contratto; alla cessazione vedi punto 8 |

## 3. Misure di sicurezza (art. 32)

Il responsabile garantisce almeno le misure già presenti nel FASAS e descritte in `docs/SICUREZZA.md`, tra cui:

- dati ospitati in data center nell'Unione europea; comunicazioni solo in HTTPS;
- verifica in due passaggi obbligatoria per amministratori, coordinatori e medici;
- documenti cifrati prima del salvataggio; chiavi conservate separate dai dati, con busta di custodia del titolare;
- audit log non modificabile con punti di controllo marcati temporalmente;
- backup giornalieri cifrati, copia fuori sede immutabile, prova di ripristino trimestrale con verbale;
- monitoraggio di funzionamento e registro errori senza dati sanitari;
- aggiornamenti di sicurezza delle dipendenze (controllo automatico settimanale) e test di sicurezza periodici.

Le misure si aggiornano con lo stato dell'arte; il responsabile informa il titolare dei cambiamenti rilevanti.

## 4. Persone autorizzate e amministratori di sistema

Il personale del responsabile accede ai dati solo quando serve (assistenza, ripristino), con credenziali personali,
impegno di riservatezza e nomina ad amministratore di sistema; gli accessi sono tracciati. Di norma l'assistenza non
richiede l'accesso alle cartelle cliniche: l'amministratore del FASAS non le vede.

## 5. Sub-responsabili

Il titolare autorizza i sub-responsabili elencati nell'allegato A. Il responsabile informa il titolare almeno
[30] giorni prima di aggiungerne o sostituirne uno; il titolare può opporsi per motivi legati alla protezione dei
dati. Il responsabile impone ai sub-responsabili gli stessi obblighi di questo accordo.

## 6. Trasferimenti fuori dall'UE

Nessun trasferimento fuori dallo Spazio economico europeo senza autorizzazione scritta del titolare e senza una
delle garanzie degli artt. 44–49 (es. clausole contrattuali tipo e valutazione d'impatto del trasferimento).

## 7. Assistenza al titolare e violazioni

- Il responsabile aiuta il titolare a rispondere alle richieste degli interessati (accesso, rettifica, copia
  della cartella: il FASAS esporta la cartella completa in PDF), alla DPIA e ai rapporti con il Garante.
- **Violazioni di dati**: comunicazione al titolare **senza ingiustificato ritardo e comunque entro [24] ore** dalla
  scoperta, con natura della violazione, dati e interessati coinvolti, conseguenze probabili e misure adottate.

## 8. Fine del contratto

Entro [30] giorni dalla cessazione il responsabile, a scelta del titolare, restituisce i dati (backup cifrato
completo con la chiave, esportazioni in PDF/Excel) e poi li cancella, incluse le copie di backup alla scadenza del
blocco delle modifiche; rilascia una dichiarazione scritta di avvenuta cancellazione.

## 9. Verifiche

Il titolare può verificare il rispetto di questo accordo, anche tramite un revisore indipendente vincolato alla
riservatezza, con preavviso di [15] giorni; il responsabile fornisce le informazioni necessarie (es. esiti dei test
di sicurezza, verbali delle prove di ripristino, registro delle modifiche delle versioni).

## Allegato A – Sub-responsabili autorizzati

| Sub-responsabile | Servizio | Sede dei dati | Garanzie |
|---|---|---|---|
| [Fornitore del server virtuale] | ospitalità di applicazione, database e file cifrati | [paese UE] | [certificazioni, DPA] |
| [Fornitore dell'object storage] | copia fuori sede dei backup **già cifrati** (il fornitore non ha la chiave) | [paese UE] | [DPA, Object Lock] |
| [Servizio email] | invio di avvisi senza dati sanitari | [paese] | [DPA] |
| [Prestatore della firma qualificata, se usato] | firma remota dei medici: riceve solo l'impronta dei documenti | [paese UE] | elenco di fiducia UE |
| [Gestore della marca temporale, se usato] | marche temporali: riceve solo impronte | [paese UE] | [qualificato eIDAS] |
