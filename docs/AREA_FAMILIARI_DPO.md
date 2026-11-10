# Area familiari e tutori – cosa valutare con il DPO prima di accenderla

L'area familiari è **spenta di default** in ogni installazione (anche in quelle già esistenti, che la ricevono
spenta con l'aggiornamento) e il pulsante «Accendi tutto» la lascia spenta. Si accende solo da *Sistema › Moduli*,
dopo il parere del DPO. Questa pagina elenca i punti da decidere; non è un parere legale.

## Cosa fa (in breve)

Persone esterne alla struttura (familiari, tutori, amministratori di sostegno) entrano nel FASAS con un utente
proprio e, per gli ospiti a cui sono collegate, scambiano messaggi con la struttura, chiedono visite, aprono i
documenti condivisi uno per uno e, se autorizzate, vedono saldo e rendiconto della cassa personale. Dettagli in
[NOVITA_ASSISTENZA_E_FAMILIARI.md](NOVITA_ASSISTENZA_E_FAMILIARI.md).

## Punti da decidere

1. **Base giuridica per ogni collegamento.** Il FASAS chiede di scriverla (consenso dell'ospite con data, decreto di
   nomina del tutore o dell'amministratore di sostegno). Il DPO indica quali basi sono ammesse, chi le verifica e
   dove si conserva l'originale (consigliato: *Documenti* dell'ospite, categoria «Documento legale»).
2. **Quali documenti si condividono.** Di default nessuno: il coordinatore li sceglie uno per uno. Il DPO indica se
   sono ammessi documenti con dati sanitari (es. relazioni) e per quali ruoli (tutore sì, familiare no?), e se serve
   il consenso dell'ospite per ciascuna categoria.
3. **Messaggi.** Possono contenere dati sanitari scritti dal personale o dal familiare: conservazione (stessa durata
   della cartella? più breve?), regole di scrittura per il personale («niente diagnosi via messaggio»), orari di
   lettura e canale per le urgenze (il FASAS ricorda di telefonare).
4. **Accesso da fuori struttura.** I familiari entrano da casa: valutare l'esposizione del FASAS su internet
   (versione cloud o accesso remoto), l'obbligo della **verifica in due passaggi** anche per il ruolo «family»
   (impostazione `FASAS_2FA_REQUIRED_ROLES`), la password minima e il blocco dopo tentativi falliti (già attivi).
5. **Valutazione d'impatto (DPIA).** Aggiornare la DPIA ([gdpr/](gdpr/)) con il nuovo trattamento: nuove categorie
   di interessati (familiari), nuovo canale, accesso remoto, notifiche email e push (che non contengono il testo
   dei messaggi né dati sanitari).
6. **Informative.** Informativa per i familiari (i loro dati: nome, email, messaggi, accessi) e aggiornamento di
   quella per gli ospiti (chi può vedere cosa).
7. **Revoca e fine del rapporto.** Chi revoca il collegamento (fine della tutela, richiesta dell'ospite, dimissione):
   con la cartella archiviata il familiare non vede più l'ospite automaticamente.
8. **Registro delle attività di trattamento.** Aggiungere il trattamento «Area familiari».

## Garanzie tecniche già presenti

- Il familiare non ha alcun permesso sulla cartella; in più un filtro su **ogni** pagina lo riporta all'area
  familiari se prova ad aprire altro (anche pagine senza permessi specifici).
- Ogni pagina dell'area verifica che il collegamento sia attivo, del familiare che la chiede e su un ospite non
  archiviato; documenti e cassa solo se il collegamento lo prevede.
- Collegamenti, messaggi, visite e condivisioni sono nell'audit (chi, quando, valori precedenti); ogni apertura di
  un documento o rendiconto è registrata.
- Le notifiche alla struttura e al familiare non riportano il testo dei messaggi.
- I familiari di uno stesso ospite non vedono le conversazioni degli altri.

## Prova consigliata prima dell'uso reale

Accenderla nell'ambiente di prova con utenti di fantasia (la presentazione online ha l'utente `familiare`), far
provare il flusso a un familiare e a un coordinatore, poi decidere con il DPO.
