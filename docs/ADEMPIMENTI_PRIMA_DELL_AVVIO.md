# Prima dei dati veri: privacy, sicurezza fisica, continuità, firma e regole

La guida tecnica ([INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md)) porta il FASAS a funzionare.
Questa pagina dice **cosa va fatto dalla struttura** prima di inserire i dati veri degli ospiti, **chi lo fa**, cosa
è già pronto e cosa costa. I documenti indicati sono **bozze da completare e far approvare**: non sono un parere
legale e non diventano validi finché il titolare (l'ente gestore) non li firma.

## In sintesi: chi fa cosa

| # | Cosa | Chi | Già pronto | Costo |
|---|---|---|---|---|
| 1 | **Responsabile della protezione dei dati (DPO/RPD)** | direzione | — | se esterno a pagamento; può essere un dipendente competente |
| 2 | Registro dei trattamenti | DPO con la direzione | [gdpr/REGISTRO_TRATTAMENTI.md](gdpr/REGISTRO_TRATTAMENTI.md) | 0 € |
| 3 | Valutazione d'impatto (DPIA) | DPO, direzione, amministratore di sistema | [gdpr/DPIA.md](gdpr/DPIA.md) | 0 € |
| 4 | Nomina dell'amministratore di sistema (e del vice) | direzione | [gdpr/MODELLO_NOMINA_AMMINISTRATORE_SISTEMA.md](gdpr/MODELLO_NOMINA_AMMINISTRATORE_SISTEMA.md) | 0 € |
| 5 | Autorizzazione scritta di ogni utente | direzione | [gdpr/MODELLO_AUTORIZZAZIONE_PERSONALE.md](gdpr/MODELLO_AUTORIZZAZIONE_PERSONALE.md) | 0 € |
| 6 | Informative a ospiti/tutori e al personale | direzione | [gdpr/INFORMATIVA_OSPITI.md](gdpr/INFORMATIVA_OSPITI.md), [gdpr/INFORMATIVA_PERSONALE.md](gdpr/INFORMATIVA_PERSONALE.md) | 0 € |
| 7 | Fornitori: Backblaze, DuckDNS, servizio di controllo | direzione con il DPO | [gdpr/RESPONSABILI_E_NOMINE.md](gdpr/RESPONSABILI_E_NOMINE.md) | 0 € |
| 8 | Procedura per le violazioni di dati (72 ore) | DPO e amministratore di sistema | [gdpr/PROCEDURA_VIOLAZIONI.md](gdpr/PROCEDURA_VIOLAZIONI.md) | 0 € |
| 9 | Sicurezza fisica e continuità (chiavi, cassaforte, sostituto) | direzione e amministratore di sistema | [SICUREZZA_FISICA_E_CONTINUITA.md](SICUREZZA_FISICA_E_CONTINUITA.md) | 0 € (serratura o cassaforte se mancano) |
| 10 | Firma con CIE: rimandarla o attivarla | direzione con il legale | [FIRMA_CIE.md](FIRMA_CIE.md) | 0 € se rimandata; polizza se attivata |
| 11 | Dispositivo medico: promemoria clinici | direzione, medico, consulente regolatorio | [DISPOSITIVO_MEDICO.md](DISPOSITIVO_MEDICO.md) | 0 € per il pilota con i promemoria spenti |
| 12 | Assicurazione | direzione con il broker | — | da verificare con la polizza attuale |
| 13 | Requisiti regionali (ATS/ASL) | direzione | [gdpr/CHECKLIST_ATS.md](gdpr/CHECKLIST_ATS.md) | 0 € |

## 1. Il DPO prima di tutto

Per le strutture sanitarie private il Garante ha indicato come obbligatorio il DPO (provvedimento del 7 marzo 2019
sui trattamenti in ambito sanitario, che cita ospedali privati, case di cura e residenze sanitarie assistenziali,
per il trattamento su larga scala di dati sanitari). Per una comunità socio-sanitaria residenziale è quindi molto
probabile che serva: **verificarlo subito**, perché il DPO deve esprimersi sulla DPIA.

- Può essere **esterno** (un professionista o una società, a pagamento) o **interno**: un dipendente con
  competenze adeguate e **senza conflitti di interesse** (non il direttore, non chi gestisce il server).
- I suoi contatti si **pubblicano** (es. nell'informativa) e si **comunicano al Garante** con la procedura online
  del sito del Garante.
- Se la struttura ha già un DPO (capita spesso per l'accreditamento), si parte da lui con questa pagina.

## 2–3. Registro e DPIA

Le bozze sono già scritte sul FASAS e su questa installazione (PC in struttura, Backblaze B2, DuckDNS, servizio di
controllo). Il DPO le legge con la direzione, compila le parti tra `[parentesi quadre]`, valuta i rischi residui e
dà il suo parere; il titolare firma la decisione di avvio. **Prima di inserire i dati veri.**

## 4–5. Nomine e autorizzazioni

- **Amministratore di sistema**: chi gestisce il server e chi lo sostituisce (passo 9), con nomina individuale,
  elenco delle attività, registrazione degli accessi e verifica annuale (provvedimento del Garante del 27/11/2008).
  Lo script d'installazione conserva gli accessi al server per circa 7 mesi e la copia mensile su disco USB ne
  porta una copia fuori dal server, con impronta per verificarne l'integrità.
- **Ogni utente del FASAS** riceve un'autorizzazione scritta con le istruzioni (password personale, verifica in
  due passaggi, telefoni, niente foto della cartella, accesso da casa solo per servizio). Il FASAS crea già
  l'utente con il ruolo giusto: il foglio firmato è la parte organizzativa.

## 6. Informative

Ospiti, tutori e amministratori di sostegno ricevono l'informativa all'ingresso (o, per chi c'è già, all'avvio del
FASAS); il personale riceve la sua, che spiega anche registrazione degli accessi e audit (art. 4 dello Statuto dei
lavoratori). Le bozze vanno completate con i dati della struttura e del DPO.

## 7. I fornitori di questa installazione

| Fornitore | Che cosa riceve | Cosa fare |
|---|---|---|
| **Backblaze** (copia fuori sede) | solo backup **già cifrati**: la chiave resta alla struttura | è un responsabile del trattamento: Backblaze dichiara che il suo accordo sul trattamento dei dati (DPA) per l'UE fa parte dei termini di servizio accettati all'iscrizione; **scaricare e archiviare** il DPA per l'UE e la data di accettazione. È una società statunitense: con il DPO verificare la base per eventuali accessi dagli USA (adesione al Data Privacy Framework UE-USA o clausole contrattuali tipo nel DPA); la cifratura con chiave della struttura riduce molto il rischio |
| **DuckDNS** (indirizzo) | l'indirizzo IP pubblico della struttura | nessun dato degli ospiti né del personale: annotarlo nel registro come servizio tecnico |
| **Servizio di controllo** (es. UptimeRobot) | l'indirizzo `/salute/` e la risposta ok/errore; l'email di chi riceve gli avvisi | nessun dato degli ospiti: annotarlo come servizio tecnico; controllare le condizioni del piano gratuito (guida, passo 16) |
| **Let's Encrypt** (certificato) | il nome dell'indirizzo | nessun dato personale |
| **GitHub** (codice del FASAS) | nulla della struttura: da lì si scarica solo il programma | nessuna azione |

## 8. Violazioni di dati

Un server rubato, un disco perso, una password rubata, un PDF della cartella mandato alla persona sbagliata: entro
**72 ore** dalla scoperta il titolare valuta e, se c'è rischio, notifica al Garante; ogni violazione va comunque
annotata nel registro interno. La procedura con la sequenza delle prime azioni e il registro è pronta.

## 9. Sicurezza fisica e continuità

Il server è nella struttura: la porta del locale, chi ne ha la chiave, cosa c'è in cassaforte e dove va il disco
mensile sono **misure di sicurezza** quanto la password. E serve **una seconda persona** che sappia usare la
guida, con le proprie credenziali (mai quelle del titolare), per ferie, malattia o cambio di lavoro. Modulo del
registro chiavi, inventario della cassaforte, scheda del sostituto e cosa fare quando un amministratore lascia:
[SICUREZZA_FISICA_E_CONTINUITA.md](SICUREZZA_FISICA_E_CONTINUITA.md).

## 10. Firma con CIE: la via gratuita è rimandarla

La firma elettronica avanzata con CIE richiede, prima dell'uso: il parere del legale sul suo uso nella struttura,
il testo delle condizioni approvato, la **polizza di responsabilità civile di almeno 500.000 €** prevista dal
DPCM 22/02/2013 (art. 57) e la prova reale con le CIE su Android e iPhone (non ancora fatta).

- **Scelta consigliata per il pilota**: lasciare spenta la firma con CIE e firmare come oggi (su carta i documenti
  che lo richiedono); i medici che hanno già una firma digitale qualificata del proprio prestatore possono usare
  quella ([FIRMA_DIGITALE.md](FIRMA_DIGITALE.md)). Il resto del FASAS funziona normalmente.
- Attivarla **dopo** parere legale, polizza e prova reale.

## 11. Regolamento sui dispositivi medici

Le funzioni che **registrano, archiviano e mostrano** i dati sono quelle più chiaramente fuori dal regolamento. I
promemoria che confrontano i dati (stesso farmaco, allergie, interazioni) sono quelli da far valutare.

- **Per il pilota**: interazioni spente (lo sono già per default); decidere con il medico se tenere accesi i
  promemoria su allergie e farmaci doppi, sapendo che sono la parte da valutare; protocolli attivi solo dopo la
  validazione del medico (già obbligatoria).
- **Prima di proporre il FASAS ad altre strutture**: parere di un consulente regolatorio con
  [DISPOSITIVO_MEDICO.md](DISPOSITIVO_MEDICO.md).

## 12. Assicurazione

- Chiedere al broker se la polizza di responsabilità civile della struttura copre anche la **tenuta digitale** del
  fascicolo e gli incidenti informatici; una polizza «cyber» è facoltativa.
- La polizza specifica della firma con CIE serve solo se la si attiva (punto 10).

## 13. ATS/ASL

Prima di sostituire la carta, presentare il FASAS digitale all'ATS con [gdpr/CHECKLIST_ATS.md](gdpr/CHECKLIST_ATS.md):
requisiti del fascicolo, vigilanza, conservazione.

---

## Calendario consigliato

| Quando | Cosa |
|---|---|
| Settimana 1 | DPO (punto 1); nomina dell'amministratore di sistema e del vice; locale e cassaforte (punto 9) |
| Settimana 2 | registro e DPIA con il DPO; decisione su firma CIE e promemoria clinici; fornitori (punto 7) |
| Settimana 3 | informative e autorizzazioni firmate; incontro con l'ATS; prova del sostituto con la guida |
| Settimane 4–7 | **pilota di 2–4 settimane accanto alla carta**, poi decisione di passare al digitale |

## Cosa non posso fare io

Ho preparato bozze, modelli e procedure. Non posso dare un parere legale, firmare, sottoscrivere contratti o
polizze, né sostituire il DPO o il consulente regolatorio: queste parti restano alla struttura.
