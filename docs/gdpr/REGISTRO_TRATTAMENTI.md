# Registro delle attività di trattamento (art. 30) – voci per FASAS Digitale

Titolare: [ente gestore] · DPO: [ ] · Data: [ ]. Ogni voce va inserita nel registro generale dell'ente.

## T1 – Cartella socio-sanitaria (FASAS)

| Campo | Contenuto |
|---|---|
| Finalità | assistenza socio-sanitaria, continuità delle cure, adempimenti per l'accreditamento |
| Base giuridica | art. 6.1.c ed e; art. 9.2.h e 9.3 GDPR; normativa regionale sull'esercizio e l'accreditamento delle unità d'offerta sociosanitarie |
| Interessati | ospiti; familiari, tutori, amministratori di sostegno |
| Categorie di dati | anagrafici e di contatto; dati relativi alla salute; disabilità; tutela legale; documenti |
| Destinatari | personale autorizzato secondo il ruolo; medici; ATS (vigilanza); struttura di destinazione in caso di trasferimento; autorità giudiziaria se richiesto |
| Responsabili (art. 28) | [hosting], [Supabase o altro DBaaS], [manutenzione software], [backup fuori sede], [prestatore firma qualificata] |
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
| Conservazione | [audit log per tutta la durata della cartella cui si riferisce; log accessi almeno 6 mesi per gli amministratori di sistema (provv. Garante 27/11/2008) – definire] |

## T5 – Notifiche sui dispositivi (facoltative)

| Campo | Contenuto |
|---|---|
| Finalità | avvisare il personale di eventi che richiedono un intervento |
| Base giuridica | art. 6.1.b e f |
| Dati | identificativo dell'iscrizione del browser, etichetta del dispositivo; il contenuto è cifrato e privo di dati sanitari |
| Destinatari | servizio push del produttore del browser (riceve solo dati cifrati) [valutare sede del fornitore] |
| Conservazione | fino alla disattivazione del dispositivo o a 5 invii falliti |
