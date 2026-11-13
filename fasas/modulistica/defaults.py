"""
Moduli predefiniti della struttura (testi sintetici, da adattare). Si caricano una sola volta alla prima
installazione (fasas_setup); poi li modifica il gestore del sistema da Sistema › Modulistica, senza toccare il codice.

Testo: paragrafi separati da una riga vuota, «- » a inizio riga per gli elenchi, **grassetto**.
Variabili: {titolare} {sede} {contatti} {dpo} {contatti_dpo} {struttura}; nei moduli del personale anche
{utente} e {ruolo}; nei moduli degli ospiti {ospite}.
Campi: (chiave, etichetta, tipo, obbligatorio, opzioni, aiuto) con tipo text, textarea, date, choice, multi,
check (una dichiarazione da spuntare) o section (un sottotitolo).
"""

ROLE_REPRESENTATIVE = ["Ospite", "Tutore", "Amministratore di sostegno", "Familiare di riferimento"]

PRIVACY_FOOTER = ("Per esercitare i diritti previsti dagli artt. 15–22 del Regolamento (UE) 2016/679 (accesso, "
                  "rettifica, limitazione, opposizione) scrivere a {contatti} o al Responsabile della protezione dei "
                  "dati ({contatti_dpo}). È possibile proporre reclamo al Garante per la protezione dei dati personali.")

TEMPLATES = [
    {
        "code": "informativa-ospiti",
        "title": "Informativa sul trattamento dei dati personali – ospiti",
        "for_guests": True, "for_family": True,
        "document_category": "form",
        "intro": """Ai sensi dell'art. 13 del Regolamento (UE) 2016/679, {titolare}, con sede in {sede}, in qualità di titolare del trattamento, informa che i dati personali dell'ospite sono trattati come segue. Responsabile della protezione dei dati: {dpo}.

**Dati e finalità.** Dati anagrafici e di contatto, dati relativi alla salute, alla disabilità e alla tutela legale, presenze e dati amministrativi, trattati per erogare l'assistenza socio-sanitaria, tenere il Fascicolo Socio Assistenziale Sanitario previsto dalla normativa regionale, adempiere agli obblighi verso ATS e Regione, gestire la retta e, se affidata alla struttura, la piccola cassa personale.

**Base giuridica.** Finalità di assistenza e cura (art. 9, par. 2, lett. h), obblighi di legge (art. 6, par. 1, lett. c) e contratto di ospitalità (art. 6, par. 1, lett. b).

**Modalità.** Sistema informatico FASAS Digitale e archivi cartacei; accesso riservato al personale autorizzato secondo il ruolo, registrazione degli accessi, cifratura dei documenti e delle copie di sicurezza.

**Destinatari.** Personale autorizzato, medici curanti, ATS e Regione, strutture di destinazione in caso di trasferimento, fornitori che gestiscono il sistema per conto del titolare (art. 28). I dati non sono diffusi.

**Conservazione.** Il fascicolo è conservato per il tempo previsto dalla normativa sanitaria e regionale; i dati amministrativi per dieci anni.

""" + PRIVACY_FOOTER,
        "fields": [
            ("nome", "Nome e cognome di chi riceve l'informativa", "text", True, [], ""),
            ("qualita", "In qualità di", "choice", True, ROLE_REPRESENTATIVE, ""),
            ("presa_visione", "Dichiaro di aver ricevuto e compreso l'informativa", "check", True, [], ""),
        ],
        "signatures": ["L'ospite o chi lo rappresenta"],
    },
    {
        "code": "informativa-personale",
        "title": "Informativa al personale sull'uso del sistema FASAS Digitale",
        "for_staff": True, "staff_roles": ["operator", "coordinator", "doctor", "administrative", "admin"],
        "auto_assign": True,
        "intro": """Ai sensi dell'art. 13 del Regolamento (UE) 2016/679 e dell'art. 4, comma 3, della L. 300/1970, {titolare} informa che il sistema FASAS Digitale, strumento di lavoro per la tenuta del fascicolo degli ospiti, registra:

- gli accessi (utente, data e ora, indirizzo IP, dispositivo, esito);
- le operazioni svolte sui dati, con il valore precedente e quello nuovo;
- turni, ferie e assenze (per la malattia solo il codice, mai la diagnosi);
- corsi di formazione e scadenze dell'idoneità alla mansione (data ed esito, senza dati clinici).

**Finalità.** Tracciabilità delle registrazioni sanitarie, sicurezza del sistema, organizzazione del lavoro e adempimenti in materia di salute e sicurezza (D.Lgs. 81/2008). Le registrazioni non sono utilizzate per il controllo a distanza dell'attività lavorativa al di fuori di quanto consentito dalla legge.

**Conservazione.** Registri degli accessi e delle operazioni per il tempo indicato nel registro dei trattamenti; dati sulla formazione per la durata del rapporto e successivamente per il tempo previsto dalla legge.

""" + PRIVACY_FOOTER,
        "fields": [
            ("presa_visione", "Dichiaro di aver ricevuto e compreso l'informativa", "check", True, [], ""),
        ],
        "signatures": ["Il/la dipendente"],
    },
    {
        "code": "autorizzazione-personale",
        "title": "Autorizzazione al trattamento dei dati e istruzioni",
        "for_staff": True, "staff_roles": ["operator", "coordinator", "doctor", "administrative"],
        "auto_assign": True,
        "intro": """{titolare}, titolare del trattamento, autorizza {utente}, con il ruolo di {ruolo}, a trattare i dati personali degli ospiti e del personale con il sistema FASAS Digitale, nei limiti necessari alle mansioni assegnate (art. 29 del Regolamento (UE) 2016/679 e art. 2-quaterdecies del D.Lgs. 196/2003).

**Istruzioni**

- Le credenziali sono personali: non vanno comunicate né usate da altri; dove richiesta, si usa la verifica in due passaggi.
- Si consultano solo i dati degli ospiti di cui ci si occupa e solo quando serve: ogni accesso è registrato.
- Non si fotografano schermate o documenti e non si salvano esportazioni su dispositivi personali.
- Si chiude la sessione o si blocca lo schermo quando ci si allontana dal dispositivo.
- Stampe ed esportazioni si conservano come la documentazione cartacea e si distruggono in modo sicuro.
- Smarrimenti, accessi sospetti o invii errati si segnalano subito al coordinatore o all'amministratore di sistema.

Quanto appreso sugli ospiti è coperto dal segreto professionale e d'ufficio anche dopo la cessazione del rapporto. L'autorizzazione vale fino a revoca, cambio di mansione o cessazione del rapporto.""",
        "fields": [
            ("accettazione", "Accetto l'autorizzazione e mi impegno a rispettare le istruzioni", "check", True, [], ""),
        ],
        "signatures": ["Il titolare del trattamento", "Il/la dipendente"],
    },
    {
        "code": "nomina-amministratore-sistema",
        "title": "Designazione ad amministratore di sistema",
        "for_staff": True, "staff_roles": ["admin"],
        "requires_signature": True, "document_category": "legal",
        "intro": """{titolare} designa {utente} amministratore di sistema per il sistema FASAS Digitale, ai sensi del provvedimento del Garante per la protezione dei dati personali del 27 novembre 2008 e successive modifiche, per gli ambiti indicati di seguito.

L'amministratore di sistema gestisce utenti, permessi, configurazione, copie di sicurezza e aggiornamenti; non accede ai dati sanitari se non per necessità tecniche documentate; custodisce le credenziali di amministrazione; segnala senza ritardo ogni possibile violazione dei dati. Gli accessi amministrativi sono registrati e l'operato è verificato almeno una volta l'anno.""",
        "fields": [
            ("ambiti", "Ambiti affidati", "multi", True,
             ["Utenti, permessi e configurazione del FASAS", "Server e sistema operativo", "Database",
              "Copie di sicurezza e ripristino", "Rete e accesso remoto"], ""),
            ("sostituto", "Sostituto (vice amministratore)", "text", False, [], ""),
            ("accettazione", "Accetto la designazione e le istruzioni ricevute", "check", True, [], ""),
        ],
        "signatures": ["Il titolare del trattamento", "L'amministratore di sistema"],
    },
    {
        "code": "cassa-e-oggetti",
        "title": "Accordo per la gestione della piccola cassa e degli oggetti personali",
        "for_guests": True,
        "requires_signature": True, "document_category": "legal",
        "intro": """Con il presente accordo {ospite} affida a {titolare} una somma per le piccole spese personali e/o gli oggetti elencati. La struttura registra ogni movimento nel sistema FASAS Digitale con data, importo e scontrino, custodisce il denaro separatamente da quello della struttura, non effettua spese oltre il saldo e i limiti indicati e fornisce un rendiconto periodico. Eventuali errori si correggono con un'annotazione motivata che resta visibile nel rendiconto.""",
        "fields": [
            ("nome", "Nome e cognome di chi sottoscrive", "text", True, [], ""),
            ("qualita", "In qualità di", "choice", True, ROLE_REPRESENTATIVE, ""),
            ("sezione_cassa", "Piccola cassa", "section", False, [], ""),
            ("limite_spesa", "Spesa singola senza autorizzazione preventiva fino a (€)", "text", False, [], ""),
            ("spese_ricorrenti", "Spese ricorrenti autorizzate", "textarea", False, [], "Es. parrucchiere mensile, bar."),
            ("rendiconto", "Rendiconto", "choice", True, ["Mensile", "Trimestrale", "Su richiesta"], ""),
            ("destinatario", "Destinatario del rendiconto e del saldo alla dimissione", "text", True, [], ""),
            ("sezione_oggetti", "Oggetti consegnati", "section", False, [], ""),
            ("oggetti", "Elenco (oggetto, descrizione, valore indicativo)", "textarea", False, [], ""),
        ],
        "signatures": ["L'ospite o chi lo rappresenta", "Per la struttura"],
    },
    {
        "code": "foto-lesioni",
        "title": "Fotografie delle lesioni cutanee – informazione e consenso",
        "for_guests": True,
        "requires_signature": True, "withdrawable": True, "document_category": "form",
        "intro": """Per seguire l'andamento delle lesioni cutanee, il personale sanitario può fotografarle durante le medicazioni. Le fotografie si scattano solo con dispositivi della struttura, inquadrano esclusivamente la lesione, sono conservate in forma cifrata nel fascicolo dell'ospite e sono consultabili solo dal personale sanitario autorizzato e dai medici curanti. Il consenso può essere revocato in qualsiasi momento senza conseguenze sull'assistenza: in tal caso le lesioni saranno documentate solo per iscritto.""",
        "fields": [
            ("nome", "Nome e cognome di chi sottoscrive", "text", True, [], ""),
            ("qualita", "In qualità di", "choice", True, ROLE_REPRESENTATIVE, ""),
            ("consenso", "Fotografie delle lesioni", "choice", True, ["Acconsento", "Non acconsento"], ""),
        ],
        "signatures": ["L'ospite o chi lo rappresenta"],
    },
    {
        "code": "richiesta-diritti",
        "title": "Richiesta di esercizio dei diritti sui dati personali",
        "for_guests": True, "for_family": True, "for_staff": True,
        "intro": """Richiesta ai sensi degli artt. 15–22 del Regolamento (UE) 2016/679, indirizzata a {titolare}. La risposta è fornita entro un mese dal ricevimento, prorogabile di due mesi nei casi complessi. Per le richieste presentate per conto di altri può essere chiesta la documentazione che ne attesta i poteri.""",
        "fields": [
            ("nome", "Nome e cognome del richiedente", "text", True, [], ""),
            ("qualita", "Per conto di", "choice", True, ["Me stesso/a", "Ospite rappresentato (tutore, amministratore di sostegno)", "Ospite deceduto (art. 2-terdecies D.Lgs. 196/2003)"], ""),
            ("richieste", "Richiedo", "multi", True,
             ["Accesso ai dati", "Copia del fascicolo", "Rettifica", "Limitazione", "Opposizione",
              "Elenco degli accessi al fascicolo", "Revoca di un consenso"], ""),
            ("dettagli", "Dettagli della richiesta", "textarea", False, [], ""),
            ("recapito", "Recapito per la risposta (indirizzo, email o PEC)", "text", True, [], ""),
        ],
        "signatures": ["Il richiedente"],
    },
    {
        "code": "informativa-familiari",
        "title": "Informativa per gli utenti dell'area familiari",
        "for_guests": True, "for_family": True,
        "intro": """Ai sensi dell'art. 13 del Regolamento (UE) 2016/679, {titolare} informa che, per l'accesso all'area familiari del sistema FASAS Digitale, tratta nome, codice fiscale e recapiti del familiare, gli estremi del documento d'identità e dell'eventuale provvedimento di nomina, i messaggi, le richieste di visita e la registrazione degli accessi.

**Finalità e base giuridica.** Comunicazioni con la struttura, programmazione delle visite e messa a disposizione delle informazioni condivise, sulla base della richiesta del familiare e del consenso dell'ospite o dei poteri conferiti dal provvedimento di nomina.

**Modalità.** Il familiare accede con credenziali personali e vede soltanto le informazioni previste per il proprio collegamento; non ha accesso alla cartella clinica. Le notifiche non contengono il testo dei messaggi né dati sanitari.

**Conservazione.** I dati dell'utente fino alla chiusura dell'accesso; messaggi e visite per il tempo indicato nel registro dei trattamenti.

""" + PRIVACY_FOOTER,
        "fields": [
            ("nome", "Nome e cognome", "text", True, [], ""),
            ("presa_visione", "Dichiaro di aver ricevuto e compreso l'informativa", "check", True, [], ""),
        ],
        "signatures": ["Il familiare"],
    },
    {
        "code": "accesso-area-familiari",
        "title": "Richiesta di accesso all'area familiari",
        "for_guests": True,
        "requires_signature": True, "document_category": "legal",
        "intro": """Richiesta di collegamento di un familiare, tutore o amministratore di sostegno a {ospite} nell'area familiari del sistema FASAS Digitale. Il collegamento consente di comunicare con la struttura e di programmare le visite; documenti condivisi e rendiconto della cassa solo se indicati di seguito. Non è mai consentito l'accesso alla cartella clinica. Le credenziali sono personali; l'accesso può essere revocato in qualsiasi momento dall'ospite capace o dalla struttura.""",
        "fields": [
            ("nome", "Nome e cognome del richiedente", "text", True, [], ""),
            ("codice_fiscale", "Codice fiscale", "text", True, [], ""),
            ("email", "Email", "text", True, [], "Recapito per le credenziali e le notifiche."),
            ("documento", "Documento d'identità (tipo e numero)", "text", True, [], ""),
            ("qualita", "Rapporto con l'ospite", "choice", True,
             ["Familiare", "Tutore", "Amministratore di sostegno", "Persona di riferimento indicata dall'ospite"], ""),
            ("base", "Base del collegamento", "choice", True,
             ["Consenso dell'ospite", "Provvedimento di nomina"], ""),
            ("estremi", "Estremi del provvedimento di nomina", "text", False, [], "Numero, data e tribunale."),
            ("accessi", "Oltre a messaggi e visite, il richiedente potrà vedere", "multi", False,
             ["Documenti condivisi dalla struttura", "Saldo e rendiconto della piccola cassa"], ""),
            ("impegni", "Mi impegno a custodire le credenziali e a non diffondere le informazioni ricevute", "check",
             True, [], ""),
        ],
        "signatures": ["Il richiedente", "L'ospite (se il collegamento si basa sul suo consenso)", "Per la struttura"],
    },
]
