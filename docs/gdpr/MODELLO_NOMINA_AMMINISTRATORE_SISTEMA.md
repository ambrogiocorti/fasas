# Designazione ad amministratore di sistema – modello

> **Bozza da completare e far rivedere al DPO.** Riferimento: provvedimento del Garante del 27 novembre 2008
> «Misure e accorgimenti prescritti ai titolari dei trattamenti effettuati con strumenti elettronici relativamente
> alle attribuzioni delle funzioni di amministratore di sistema», come modificato il 25 giugno 2009. Una lettera
> per ogni persona (titolare del ruolo e vice). Le parti tra `[parentesi quadre]` vanno compilate.

---

**[Ente gestore]**, [sede], in qualità di titolare del trattamento, in persona di [legale rappresentante]

**a** [nome e cognome], [ruolo in struttura]

**Oggetto: designazione ad amministratore di sistema del FASAS Digitale**

### 1. Valutazione

Il titolare, valutate l'esperienza, la capacità e l'affidabilità della persona sopra indicata, la designa
amministratore di sistema [titolare / vice] per il sistema FASAS Digitale della struttura, a decorrere dal [data].

### 2. Ambito delle attività consentite

- **Server FASAS**: accensione e spegnimento, sistema operativo, firewall, aggiornamenti, Docker e servizi del FASAS,
  secondo `docs/INSTALLAZIONE_IN_STRUTTURA.md`.
- **Backup**: controllo dei backup notturni, copia mensile su disco USB, prova di ripristino trimestrale, copia
  fuori sede su Backblaze B2.
- **Chiavi e segreti**: creazione e custodia della busta delle chiavi; conoscenza della frase di cifratura del
  disco [sì/no], della password di GRUB e del BIOS [sì/no].
- **Account tecnici della struttura**: DuckDNS, Backblaze, servizio di controllo, pannello del router [elencare].
- **FASAS – amministrazione applicativa**: creazione e disattivazione degli utenti, ruoli e permessi,
  reimpostazione della verifica in due passaggi, configurazione. **Il ruolo di amministratore del FASAS non dà
  accesso alla cartella clinica degli ospiti**; l'accesso ai dati sanitari non rientra in questa designazione.
- Sono escluse le attività non elencate; se servono, si chiedono per iscritto al titolare.

### 3. Istruzioni

1. Usare solo **credenziali personali**: un proprio utente sul server e un proprio utente nel FASAS, con
   verifica in due passaggi. Mai usare o comunicare le credenziali di altri.
2. Accedere al server **solo dalla rete della struttura** e solo quando serve per le attività del punto 2.
3. Non copiare dati del FASAS fuori dai supporti previsti (disco USB dei backup, chiavetta della busta).
4. Custodire frasi segrete e codici di recupero come previsto in `docs/SICUREZZA_FISICA_E_CONTINUITA.md`.
5. Segnalare **subito** al titolare e al DPO ogni anomalia o possibile violazione di dati
   (`docs/gdpr/PROCEDURA_VIOLAZIONI.md`).
6. Seguire il calendario di manutenzione (guida, passo 18) e annotarne l'esecuzione.
7. Mantenere la riservatezza su quanto conosciuto nello svolgimento dell'incarico, anche dopo la sua fine.

### 4. Registrazione degli accessi

Gli accessi dell'amministratore di sistema sono registrati:

- **server**: accessi SSH e uso di `sudo` in `/var/log/auth.log`, conservati circa 7 mesi sul server; una copia
  mensile con impronta SHA-256 viene salvata sul disco USB dei backup (`scripts/copia_backup_usb.sh`), tenuto fuori
  dal locale del server;
- **FASAS**: registro degli accessi (utente, data e ora, indirizzo, dispositivo, esito) e audit delle operazioni,
  con catena di impronte che rende rilevabili le modifiche.

[Il DPO valuta se queste registrazioni hanno completezza, inalterabilità e verificabilità adeguate, come chiede il
provvedimento, e se conservarle oltre i 6 mesi minimi.]

### 5. Verifica dell'operato

Il titolare, anche tramite il DPO, verifica **almeno una volta l'anno** l'operato dell'amministratore di sistema:
calendario di manutenzione eseguito, verbali delle prove di ripristino, registro delle chiavi e dei supporti,
elenco degli utenti attivi del FASAS, controllo a campione delle registrazioni di accesso. L'esito è verbalizzato.

### 6. Elenco e conoscibilità

Il nominativo è inserito nell'**elenco interno degli amministratori di sistema** con le funzioni attribuite.
Poiché il FASAS contiene anche dati del personale (turni, accessi), l'identità degli amministratori di sistema è resa
nota al personale [modalità: bacheca, intranet, informativa al personale].

### 7. Durata e revoca

La designazione vale fino a revoca o alla cessazione del rapporto. Alla cessazione si applica la lista di controllo
«Quando un amministratore lascia» in `docs/SICUREZZA_FISICA_E_CONTINUITA.md`.

[Luogo, data]

Il titolare: ______________________   Per accettazione, l'amministratore di sistema: ______________________

---

## Elenco interno degli amministratori di sistema

| Nome e cognome | Ruolo (titolare/vice) | Funzioni (punto 2) | Dal | Al | Ultima verifica annuale |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
