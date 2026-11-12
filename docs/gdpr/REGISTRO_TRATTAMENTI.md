# Registro delle attività di trattamento (art. 30) – voci per FASAS Digitale

Titolare: [ente gestore] · DPO: [ ] · Data: [ ]. Ogni voce va inserita nel registro generale dell'ente.

## T1 – Cartella socio-sanitaria (FASAS)

| Campo | Contenuto |
|---|---|
| Finalità | assistenza socio-sanitaria, continuità delle cure, adempimenti per l'accreditamento |
| Base giuridica | art. 6.1.c ed e; art. 9.2.h e 9.3 GDPR; normativa regionale sull'esercizio e l'accreditamento delle unità d'offerta sociosanitarie |
| Interessati | ospiti; familiari, tutori, amministratori di sostegno (anche come utenti dell'area familiari, se attivata – T8) |
| Categorie di dati | anagrafici e di contatto; dati relativi alla salute; disabilità; tutela legale; documenti |
| Destinatari | personale autorizzato secondo il ruolo; medici; ATS (vigilanza); struttura di destinazione in caso di trasferimento; autorità giudiziaria se richiesto |
| Responsabili (art. 28) | [hosting], [Supabase o altro DBaaS], [manutenzione software], [backup fuori sede], [prestatore firma qualificata]. Con l'installazione in struttura: **Backblaze** (copia fuori sede dei backup già cifrati, regione UE); server di proprietà della struttura, nessun hosting esterno |
| Trasferimenti extra-UE | nessuno previsto: [verificare regione e sub-responsabili dei fornitori] |
| Conservazione | [secondo normativa regionale; per la documentazione sanitaria la prassi è la conservazione illimitata (circolare del Ministero della Sanità 19/12/1986 n. 900.2/2.7/190) – da verificare con l'ATS]; in FASAS: «conservazione cartelle archiviate (anni)» in Configurazione |
| Misure di sicurezza | vedi [docs/SICUREZZA.md](../SICUREZZA.md) e DPIA |

## T2 – Presenze per la rendicontazione e rette

| Campo | Contenuto |
|---|---|
| Finalità | rendicontazione delle presenze ad ATS/Regione; determinazione e incasso delle rette |
| Base giuridica | art. 6.1.b e c; art. 9.2.h per i giorni di ricovero ospedaliero (dato sanitario indiretto) |
| Interessati | ospiti; paganti (familiari, ADS) |
| Dati | anagrafica, codice fiscale, giorni di presenza e assenza per tipo, importi, dati dei paganti, incassi |
| Destinatari | ATS/Regione; Comuni; paganti; consulente fiscale/commercialista [nomina]; istituto bancario |
| Conservazione | 10 anni per la documentazione contabile (art. 2220 c.c.) [verificare] |

## T3 – Organizzazione del personale (turni)

| Campo | Contenuto |
|---|---|
| Finalità | pianificazione dei turni, ferie, permessi, sostituzioni |
| Base giuridica | art. 6.1.b e c; art. 88 GDPR e normativa sul lavoro; per la malattia art. 9.2.b (solo il codice di assenza, nessuna diagnosi) |
| Interessati | operatori, coordinatori |
| Dati | turni, ore pianificate, ferie, permessi, assenze per malattia (solo codice), richieste di cambio |
| Destinatari | coordinatore; ufficio amministrativo/paghe; consulente del lavoro [nomina] |
| Conservazione | [5 anni dopo la cessazione del rapporto – verificare con il consulente del lavoro] |

## T4 – Sicurezza e tracciabilità del sistema

| Campo | Contenuto |
|---|---|
| Finalità | sicurezza informatica, tracciabilità legale delle registrazioni sanitarie, prevenzione degli accessi abusivi |
| Base giuridica | art. 6.1.c e f; art. 32 GDPR; art. 4 c. 2–3 L. 300/1970 (strumenti di lavoro, con informativa) |
| Interessati | utenti del sistema |
| Dati | log accessi (utente, data e ora, IP, dispositivo, esito); audit log delle operazioni |
| Destinatari | amministratore di sistema; DPO; autorità se richiesto |
| Conservazione | [audit log per tutta la durata della cartella cui si riferisce; log accessi almeno 6 mesi per gli amministratori di sistema (provv. Garante 27/11/2008) – definire]. Installazione in struttura: accessi al server (SSH, sudo) circa 7 mesi sul server, più una copia mensile con impronte sul disco USB dei backup |
| Servizi tecnici senza dati degli ospiti | DuckDNS (riceve l'IP pubblico della struttura); servizio di controllo del funzionamento (indirizzo `/salute/` ed email di chi riceve gli avvisi); Let's Encrypt (nome dell'indirizzo per il certificato) |

## T5 – Notifiche sui dispositivi (facoltative)

| Campo | Contenuto |
|---|---|
| Finalità | avvisare il personale di eventi che richiedono un intervento |
| Base giuridica | art. 6.1.b e f |
| Dati | identificativo dell'iscrizione del browser, etichetta del dispositivo; il contenuto è cifrato e privo di dati sanitari |
| Destinatari | servizio push del produttore del browser (riceve solo dati cifrati) [valutare sede del fornitore] |
| Conservazione | fino alla disattivazione del dispositivo o a 5 invii falliti |

## T6 – Denaro e oggetti personali degli ospiti

| Campo | Contenuto |
|---|---|
| Finalità | custodia e gestione della piccola cassa personale dell'ospite e degli oggetti consegnati alla struttura; rendiconto al tutore, all'amministratore di sostegno o al familiare che versa |
| Base giuridica | art. 6.1.b (accordo di gestione della cassa con l'ospite o il suo rappresentante – modulo «Accordo per la piccola cassa» della Modulistica); art. 6.1.c per gli obblighi di rendiconto del tutore o dell'amministratore di sostegno |
| Interessati | ospiti; familiari, tutori e amministratori di sostegno che versano o ricevono denaro |
| Dati | movimenti (data, importo, descrizione, da/a chi), foto o PDF degli scontrini, inventario degli oggetti con valore indicativo; **nessun dato sanitario** |
| Destinatari | personale autorizzato (operatori per le spese, coordinatore, ufficio amministrativo); tutore o amministratore di sostegno (rendiconto); giudice tutelare se richiesto |
| Conservazione | [10 anni per la documentazione contabile – verificare; oppure fino al rendiconto finale approvato dopo la dimissione] |
| Misure | scontrini cifrati con impronta, ridotti e senza dati di posizione; movimenti non cancellabili (annullamento con motivo); audit di ogni apertura e rendiconto |

## T7 – Formazione e idoneità del personale

| Campo | Contenuto |
|---|---|
| Finalità | verifica degli obblighi di formazione (sicurezza, BLSD, antincendio, primo soccorso, preposto, HACCP) e dell'idoneità alla mansione; avvisi di scadenza |
| Base giuridica | art. 6.1.c (D.Lgs. 81/2008 artt. 18, 37, 41; requisiti di accreditamento); art. 9.2.b e art. 88 GDPR per il **giudizio di idoneità** (dato relativo alla salute del lavoratore, solo nella forma consegnata al datore di lavoro) |
| Interessati | personale dipendente e collaboratori |
| Dati | tipo di corso o visita, data, scadenza, ente o medico, attestato (cifrato); per l'idoneità solo data, scadenza ed esito sintetico, **mai** diagnosi o cartella sanitaria e di rischio |
| Destinatari | coordinatore, ufficio amministrativo/personale, il diretto interessato; RSPP e medico competente; ATS in sede di vigilanza |
| Conservazione | [per la durata del rapporto e [5/10] anni dopo – verificare con il consulente del lavoro e l'RSPP] |

## T8 – Area familiari e tutori (solo se attivata, dopo il parere del DPO)

| Campo | Contenuto |
|---|---|
| Finalità | comunicazioni tra la struttura e familiari, tutori o amministratori di sostegno; programmazione delle visite; condivisione di documenti scelti; rendiconto della cassa al tutore |
| Base giuridica | [da definire con il DPO]: consenso dell'ospite capace (art. 6.1.a e 9.2.a) oppure poteri del tutore o dell'amministratore di sostegno (decreto di nomina); art. 6.1.b per la programmazione delle visite |
| Interessati | ospiti; familiari, tutori, amministratori di sostegno (utenti dell'area) |
| Dati | dati dell'utente familiare (nome, email, accessi), messaggi, richieste di visita, documenti condivisi uno per uno, saldo e rendiconto della cassa se previsto |
| Destinatari | coordinatore e personale autorizzato; il familiare collegato (solo per l'ospite e le informazioni previste dal collegamento) |
| Conservazione | [messaggi e visite: definire con il DPO, es. 2 anni o fino all'archiviazione della cartella]; accessi come T4 |
| Misure | modulo spento finché non viene acceso; collegamento con base giuridica scritta; ogni familiare vede solo il proprio collegamento; nessun'altra pagina del FASAS accessibile; notifiche senza il testo dei messaggi; audit di ogni apertura |
