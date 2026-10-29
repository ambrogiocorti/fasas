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
| Strumenti | FASAS Digitale (applicazione web Django) su [server/hosting], database PostgreSQL su [Supabase, regione UE …], file cifrati su [disco del server / object storage]; tablet e PC di reparto; telefoni personali per le notifiche (facoltative) |
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
| R1 | Accesso non autorizzato alla cartella (credenziali rubate o condivise) | media | alta | password robuste, blocco dopo tentativi falliti, disconnessione per inattività, restrizione per rete, log accessi con IP e dispositivo, permessi per ruolo | utenze personali mai condivise; disattivazione immediata a fine rapporto; **autenticazione a due fattori** (in roadmap) | medio → basso con 2FA |
| R2 | Consultazione eccedente da parte di personale autorizzato | media | media | ruoli minimi, audit log di consultazioni e download, documenti con registro degli accessi | verifica periodica a campione dell'audit log da parte del coordinatore/DPO | basso |
| R3 | Alterazione o cancellazione di registrazioni sanitarie | bassa | alta | audit log non modificabile con catena di hash e trigger sul database, annullamento invece di cancellazione, chiusura turno | procedura per le correzioni | basso |
| R4 | Perdita di dati (guasto, ransomware, errore) | media | alta | backup giornaliero cifrato AES-256-GCM con verifica di integrità, ripristino documentato | **copia fuori sede immutabile** (da decidere, vedi roadmap), prova di ripristino trimestrale, custodia delle chiavi in due luoghi | medio → basso |
| R5 | Indisponibilità (rete o server fuori uso) durante l'assistenza | media | alta | modalità senza rete cifrata, foglio di emergenza stampabile, sincronizzazione con ora reale | procedura di emergenza, stampa quotidiana del foglio | basso |
| R6 | Furto o smarrimento di un tablet o telefono | media | media | dati sul dispositivo cifrati e apribili solo con la password; blocco per inattività; nessuna pagina sanitaria nella cache; push senza dati | blocco schermo obbligatorio, profilo browser dedicato, inventario dei dispositivi | basso |
| R7 | Divulgazione tramite notifiche, email, schermate di blocco | media | media | notifiche senza nomi né dati clinici (default) | non attivare `FASAS_PUSH_SHOW_DETAILS` sui dispositivi condivisi | basso |
| R8 | Trasferimento o accesso del fornitore cloud | bassa | alta | database con RLS e revoca dei ruoli API, connessione TLS, file e backup cifrati prima dell'invio | **regione UE**, contratto art. 28 con i fornitori, valutazione dei sub-responsabili | basso |
| R9 | Errori di importazione dal cartaceo (terapie errate) | media | alta | anteprima con controlli, avvisi su duplicati/interazioni/allergie, audit di origine «import» | **verifica medica** delle terapie importate prima del primo giro farmaci | basso |
| R10 | Uso improprio del firmatario remoto | bassa | alta | firma solo con PIN/OTP personali non salvati; impronte vincolate; audit della firma | custodia personale delle credenziali del prestatore | basso |
| R11 | Controllo a distanza del personale (audit e log accessi) | media | media | log usati per sicurezza e tracciabilità sanitaria | **informativa al personale** (art. 4 c. 3 L. 300/1970), uso dei log solo per le finalità dichiarate | basso |

## 5. Parere del DPO e decisione

- Parere del DPO: [ ]
- Opinione degli interessati o dei loro rappresentanti (se raccolta): [ ]
- Decisione del titolare: [avvio / avvio con condizioni / consultazione preventiva del Garante (art. 36) se il
  rischio residuo resta alto]
- Firma del titolare: [ ]
