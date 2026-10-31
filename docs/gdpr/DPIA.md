# Valutazione d'impatto sulla protezione dei dati (DPIA) – bozza

**Titolare**: [ente gestore, sede, CF/P.IVA] · **DPO/RPD**: [nome, contatti] · **Redatta da**: [ ] il [ ] ·
**Versione**: 0.1 (bozza) · **Prossimo riesame**: entro 12 mesi o a ogni modifica rilevante del sistema

## 1. Perché è necessaria

Il trattamento riguarda **dati relativi alla salute** (art. 9 GDPR) di **persone vulnerabili** (persone con
disabilità, spesso con tutore o amministratore di sostegno), con **monitoraggio sistematico** (diario, parametri,
eventi, contenzioni) e l'uso di **tecnologie nuove** per la struttura (applicazione web, dispositivi mobili, firma
remota, lavoro senza rete). Ricorrono quindi più criteri delle Linee guida WP29 sulla DPIA (WP248 rev.01) e
l'elenco del Garante dei trattamenti soggetti a DPIA (provvedimento n. 467 dell'11 ottobre 2018): la DPIA va
svolta prima dell'avvio. [Verificare con il DPO.]

## 2. Descrizione sistematica del trattamento

| Voce | Contenuto |
|---|---|
| Finalità | tenuta del Fascicolo Socio Assistenziale Sanitario (FASAS); erogazione dell'assistenza; continuità delle cure; adempimenti verso ATS/Regione (rendicontazione presenze); gestione amministrativa delle rette; organizzazione del personale (turni); sicurezza del sistema |
| Interessati | ospiti; familiari, tutori, amministratori di sostegno; medici esterni; personale della struttura |
| Dati | anagrafici, di contatto, codice fiscale e tessera sanitaria; dati sanitari (diagnosi, allergie, terapie e somministrazioni, parametri, eventi, contenzioni, PAI, referti e documenti); dati su disabilità e tutela legale; presenze e rette; per il personale: turni, ferie, accessi e operazioni svolte |
| Strumenti | FASAS Digitale (applicazione web Django) su [server/hosting], database PostgreSQL su [Supabase, regione UE …], file cifrati su [disco del server / object storage]; tablet e PC di reparto; telefoni personali per le notifiche (facoltative). **Installazione in struttura** ([INSTALLAZIONE_IN_STRUTTURA.md](../INSTALLAZIONE_IN_STRUTTURA.md)): PC dedicato con Ubuntu Server e disco cifrato (LUKS, sblocco con TPM), in locale chiuso, raggiungibile da internet solo in HTTPS sulle porte 80/443 tramite indirizzo DuckDNS; backup cifrati ogni notte con copia fuori sede su Backblaze B2 (regione UE, non cancellabile per 14 giorni) e copia mensile su disco USB custodito altrove; controllo di funzionamento esterno sull'indirizzo `/salute/` |
| Flussi verso terzi | ATS/Regione (presenze, vigilanza); medici curanti; struttura di destinazione in caso di trasferimento (esportazione della cartella); Comuni e paganti (prospetti di retta, senza dati sanitari); prestatore di firma qualificata (solo impronta del documento) |
| Conservazione | vedi registro dei trattamenti e [CHECKLIST_ATS.md](CHECKLIST_ATS.md) |

## 3. Necessità e proporzionalità

- **Basi giuridiche**: art. 9.2.h GDPR (assistenza sanitaria e sociale) con obbligo di segreto (art. 9.3) e normativa
  regionale sull'accreditamento; art. 6.1.c (obblighi legali, rendicontazione); art. 6.1.b (contratto di
  ospitalità e di lavoro). [Verificare se servono consensi specifici, es. per foto o comunicazioni a familiari.]
- **Minimizzazione**: ogni ruolo vede solo ciò che gli serve – l'amministratore di sistema e l'ufficio
  amministrativo **non** accedono alla cartella clinica; notifiche push ed email senza nomi né dati sanitari;
  i prospetti di retta riportano solo i giorni di presenza/assenza.
- **Esattezza**: registrazioni con autore e ora; correzioni tracciate; dopo 24 ore modifiche solo con motivazione.
- **Limitazione della conservazione**: cartelle archiviate con data di conservazione; report eliminati dopo 1–5 anni
  configurabili; file temporanei (importazioni, pacchetti offline) cancellati automaticamente.
- **Diritti degli interessati**: accesso e copia tramite l'esportazione completa della cartella in PDF;
  rettifica tramite le correzioni tracciate; [procedura per le richieste: a chi, entro 30 giorni].

## 4. Rischi e misure

Scala: probabilità e gravità *bassa / media / alta*. Il rischio residuo è quello stimato dopo le misure.

| # | Rischio | Prob. | Grav. | Misure presenti in FASAS | Misure organizzative da adottare | Residuo |
|---|---|---|---|---|---|---|
| R1 | Accesso non autorizzato alla cartella (credenziali rubate o condivise) | media | alta | password robuste, blocco dopo tentativi falliti, disconnessione per inattività, log accessi con IP e dispositivo, permessi per ruolo, **verifica in due passaggi** obbligatoria per amministratori, coordinatori e medici e per tutti da fuori struttura, attivabile solo dalla rete interna | utenze personali mai condivise ([MODELLO_AUTORIZZAZIONE_PERSONALE.md](MODELLO_AUTORIZZAZIONE_PERSONALE.md)); disattivazione immediata a fine rapporto | basso |
| R2 | Consultazione eccedente da parte di personale autorizzato | media | media | ruoli minimi, audit log di consultazioni e download, documenti con registro degli accessi | verifica periodica a campione dell'audit log da parte del coordinatore/DPO | basso |
| R3 | Alterazione o cancellazione di registrazioni sanitarie | bassa | alta | audit log non modificabile con catena di hash e trigger sul database, annullamento invece di cancellazione, chiusura turno | procedura per le correzioni | basso |
| R4 | Perdita di dati (guasto, ransomware, errore) | media | alta | backup giornaliero cifrato AES-256-GCM con verifica di integrità; copia fuori sede non cancellabile (Object Lock); prova di ripristino trimestrale automatica con verbale; busta di custodia delle chiavi | copia mensile su disco USB scollegato e custodito altrove; verifica dei verbali; prova annuale della busta | basso |
| R5 | Indisponibilità (rete o server fuori uso) durante l'assistenza | media | alta | modalità senza rete cifrata, foglio di emergenza stampabile, sincronizzazione con ora reale | procedura di emergenza, stampa quotidiana del foglio | basso |
| R6 | Furto o smarrimento di un tablet o telefono | media | media | dati sul dispositivo cifrati e apribili solo con la password; blocco per inattività; nessuna pagina sanitaria nella cache; push senza dati | blocco schermo obbligatorio, profilo browser dedicato, inventario dei dispositivi | basso |
| R7 | Divulgazione tramite notifiche, email, schermate di blocco | media | media | notifiche senza nomi né dati clinici (default) | non attivare `FASAS_PUSH_SHOW_DETAILS` sui dispositivi condivisi | basso |
| R8 | Trasferimento o accesso del fornitore cloud | bassa | alta | database con RLS e revoca dei ruoli API, connessione TLS, file e backup cifrati prima dell'invio | **regione UE**, contratto art. 28 con i fornitori, valutazione dei sub-responsabili | basso |
| R9 | Errori di importazione dal cartaceo (terapie errate) | media | alta | anteprima con controlli, avvisi su duplicati/interazioni/allergie, audit di origine «import» | **verifica medica** delle terapie importate prima del primo giro farmaci | basso |
| R10 | Uso improprio del firmatario remoto | bassa | alta | firma solo con PIN/OTP personali non salvati; impronte vincolate; audit della firma | custodia personale delle credenziali del prestatore | basso |
| R11 | Controllo a distanza del personale (audit e log accessi) | media | media | log usati per sicurezza e tracciabilità sanitaria | **informativa al personale** (art. 4 c. 3 L. 300/1970), uso dei log solo per le finalità dichiarate | basso |
| R12 | Furto del server o accesso fisico al locale | bassa | alta | disco cifrato; sblocco automatico solo con l'avvio originale; password di BIOS e GRUB, avvio da USB disattivato | locale chiuso con registro delle chiavi ([SICUREZZA_FISICA_E_CONTINUITA.md](../SICUREZZA_FISICA_E_CONTINUITA.md)); in caso di furto procedura violazioni | basso [il DPO valuti il rischio residuo dello sblocco automatico rispetto alla frase digitata a ogni avvio] |
| R13 | Attacchi dall'esterno (pagina di accesso esposta su internet, vulnerabilità) | media | alta | solo HTTPS, firewall con le sole porte 80/443, blocco dopo tentativi falliti, verifica in due passaggi, aggiornamenti di sicurezza automatici del sistema, dipendenze controllate a ogni modifica | aggiornamento del FASAS alle nuove versioni; test di sicurezza esterno prima della messa in produzione | medio → basso dopo il test |
| R14 | Incendio, allagamento, guasto elettrico nel locale del server | bassa | alta | gruppo di continuità con spegnimento ordinato; copia fuori sede ogni notte | copia mensile custodita in altro luogo; estintore adatto; locale idoneo | basso |
| R15 | Dipendenza da una sola persona per la gestione del server | media | media | guida d'installazione e manutenzione scritta; prove automatiche | vice amministratore nominato e addestrato, scheda del sostituto | basso |
| R16 | Furto degli account tecnici (DuckDNS, Backblaze, router) | bassa | media | i backup su Backblaze sono cifrati con chiave della struttura e non cancellabili per 14 giorni | account intestati alla struttura con verifica in due passaggi; password nel gestore della struttura | basso |
| R17 | Violazione non rilevata o non notificata in tempo | media | alta | avvisi automatici (backup, audit, errori, controllo esterno) | [PROCEDURA_VIOLAZIONI.md](PROCEDURA_VIOLAZIONI.md) con registro interno | basso |

## 5. Parere del DPO e decisione

- Parere del DPO: [ ]
- Opinione degli interessati o dei loro rappresentanti (se raccolta): [ ]
- Decisione del titolare: [avvio / avvio con condizioni / consultazione preventiva del Garante (art. 36) se il
  rischio residuo resta alto]
- Firma del titolare: [ ]
