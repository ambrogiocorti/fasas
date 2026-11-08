# Roadmap

Stato al 08/11/2026, versione 0.10.0 «pilota» ([CHANGELOG](../CHANGELOG.md)). ✅ fatto · 🟡 da decidere o da completare fuori dal software · ⬜ da fare

> **Blocco delle funzioni fino alla fine del pilota.** Dalla 0.10.0 si fanno solo correzioni di errori e dei punti
> scomodi segnalati con «Segnala un problema». Le voci ⬜ delle fasi 2 e 3 si riprendono dopo la 1.0, scegliendole
> in base all'uso reale ([PIANO_PILOTA.md](PIANO_PILOTA.md)).

## Fase 1 – Prima di inserire dati reali

| | Attività | Note |
|---|---|---|
| ✅ | Versione online su un solo codice: VPS (`prepara_server.sh --vps`), pubblicazione da GitHub con ritorno automatico, versione cloud con Supabase | [FASAS_ONLINE.md](FASAS_ONLINE.md), [CLOUD.md](CLOUD.md); provate nella CI |
| 🟡 | **fasas.online operativo**: acquisto del VPS, record DNS su Register.it, dominio tolto da GitHub Pages, segreti per la pubblicazione | decisione e spesa della struttura (circa 6–8 €/mese), passi 1–6 di [FASAS_ONLINE.md](FASAS_ONLINE.md) |
| ✅ | Importazione dal FASAS cartaceo | modello Excel con anteprima degli errori, scansioni abbinate all'ospite – [IMPORTAZIONE.md](IMPORTAZIONE.md) |
| ✅ | Firma digitale remota qualificata | API CSC, PIN + OTP, PAdES con marca temporale – [FIRMA_DIGITALE.md](FIRMA_DIGITALE.md). Serve il contratto con un prestatore e una prova nella sua sandbox |
| 🟡 | Firma elettronica avanzata con CIE (FASAS Sign) | server, interfaccia e FASAS Signer pronti e provati con PKCS#11 reale (SoftHSM); accettazione delle condizioni firmata con la CIE e conservata 20 anni (art. 57) – [FIRMA_CIE.md](FIRMA_CIE.md). **Da collaudare con una CIE reale**; testo delle condizioni da far approvare al legale; assicurazione dell'erogatore |
| ✅ | Lavoro senza rete e foglio di emergenza | [NOTIFICHE_E_SENZA_RETE.md](NOTIFICHE_E_SENZA_RETE.md) |
| 🟡 | Backup fuori sede | software pronto e provato (object storage S3 con Object Lock, prova di ripristino trimestrale con verbale) – [BACKUP.md](BACKUP.md). **Scelto Backblaze B2** (regione UE, piano gratuito fino a 10 GB): da aprire l'account intestato alla struttura e archiviare il DPA |
| ✅ | Autenticazione a due fattori | obbligatoria per amministratore, coordinatore, medico e per gli accessi da fuori rete |
| ✅ | Verifica notturna dell'audit log con risultato salvato | punti di controllo con marca temporale RFC 3161 (se c'è una TSA), ricevuta verificabile con OpenSSL |
| ✅ | Installazione in struttura | guida passo passo con lista della spesa, script `prepara_server.sh` provato nella CI, copia mensile su disco USB – [INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md) |
| ✅ | Avvio di prova sicuro | controllo dei soli dati di fantasia, fascia rossa con le chiavi di sviluppo, API spenta per default, firma remota nascosta finché non configurata |
| ✅ | Controlli unici sulle somministrazioni | dose prescritta, giorno, orario, turno, duplicati e limiti dei SOS uguali da web, API e senza rete; la struttura sceglie conferma motivata o blocco |
| ✅ | Protocolli con campi guidati | niente testo JSON; azioni fissate all'attivazione e spuntabili una sola volta |
| ✅ | Evacuazioni distinte | avvenuta, verificata non avvenuta, non documentata, assenza |
| ✅ | Test delle schermate | viste coperte al 91% (quelle del turno sopra l'83%), comandi di backup e ripristino |
| ✅ | Installazione ripetibile | versione 0.9.0, dipendenze con impronte, immagine Docker e compose con HTTPS provati nella CI – [CONTAINER.md](CONTAINER.md) |
| ✅ | Monitoraggio | `/salute/`, job sorvegliati, registro errori senza dati sanitari – [MONITORAGGIO.md](MONITORAGGIO.md) |
| ✅ | Custodia delle chiavi | segreti da file, verifica delle chiavi, busta di custodia cifrata – [SICUREZZA.md](SICUREZZA.md#custodia-delle-chiavi) |
| ✅ | Prova di carico | 20 operatori contemporanei, 60 ospiti: 95% delle pagine sotto 0,6 s – [PRESTAZIONI.md](PRESTAZIONI.md) |
| 🟡 | Dispositivo medico (MDR) | promemoria configurabili, interazioni spente fino al parere, validazione del medico – [DISPOSITIVO_MEDICO.md](DISPOSITIVO_MEDICO.md). **Serve il parere di un consulente regolatorio** |
| ⬜ | Test di penetrazione esterno | da affidare a un soggetto indipendente prima del pilota |
| 🟡 | GDPR: registro, DPIA, informative, nomine | bozze pronte in [gdpr/](gdpr/README.md), compreso l'accordo art. 28 con il fornitore; da completare con DPO/consulente |
| 🟡 | Requisiti FASAS regionali e conservazione | checklist per l'ATS in [gdpr/CHECKLIST_ATS.md](gdpr/CHECKLIST_ATS.md) |
| 🟡 | Validazione clinica di protocolli e interazioni | pulsante «Valida» del medico: prima i protocolli non si attivano e le interazioni non entrano nei promemoria |
| 🟡 | Pilota | un nucleo, 5-8 utenti, 4-6 settimane accanto al cartaceo, con indicatori, segnalazioni e criteri per andare avanti o fermarsi – [PIANO_PILOTA.md](PIANO_PILOTA.md); schede per ruolo in [guide/](guide/OPERATORE.md) |
| ✅ | Moduli accendibili e configurazione per il pilota | Configurazione › Moduli: i moduli facoltativi si spengono senza perdere dati |
| ✅ | Segnalazioni e indicatori del pilota | «Segnala un problema» in ogni pagina; giro farmaci, registrazioni mancanti e in ritardo, checklist |
| ✅ | Pacchetto per l'ispezione | un PDF per la vigilanza ATS/ASL, archiviato come i report |
| ✅ | App Android distribuita dal FASAS | APK firmato con la chiave della struttura, QR code, avviso di aggiornamento – [FIRMA_CIE.md](FIRMA_CIE.md) |
| ✅ | Accessibilità | controllo automatico WCAG 2.1 A/AA nella CI, testo più grande per utente; prova con le persone nel pilota |
| ✅ | Continuità del fornitore | [SECONDO_TECNICO.md](SECONDO_TECNICO.md) e [MODELLO_CONTRATTO_ASSISTENZA.md](MODELLO_CONTRATTO_ASSISTENZA.md) |
| 🟡 | Sicurezza fisica e continuità | modelli pronti – [SICUREZZA_FISICA_E_CONTINUITA.md](SICUREZZA_FISICA_E_CONTINUITA.md); locale, cassaforte e vice amministratore a cura della struttura |

## Fase 2 – Miglioramenti di grande utilità

| | Attività | Note |
|---|---|---|
| ✅ | Notifiche push sul telefono | senza dati sanitari sulla schermata di blocco |
| ✅ | Presenze per la rendicontazione, rette, prospetti, incassi | [PRESENZE_E_RETTE.md](PRESENZE_E_RETTE.md); ruolo Amministrativo |
| ✅ | Pianificazione mensile dei turni, ferie, cambi turno | [TURNI_DEL_PERSONALE.md](TURNI_DEL_PERSONALE.md) |
| ✅ | Scale di valutazione con rivalutazione | Barthel, Braden, Norton, Tinetti, PAINAD, NRS; collegate al PAI – [VALUTAZIONI_E_LESIONI.md](VALUTAZIONI_E_LESIONI.md) |
| ✅ | Lesioni da pressione e medicazioni | categoria, misure, foto cifrate, piano e scadenze – [VALUTAZIONI_E_LESIONI.md](VALUTAZIONI_E_LESIONI.md) |
| ✅ | Report configurabili | modelli con sezioni, colonne e ordine; PDF ed Excel; ogni N giorni |
| ✅ | Token API con scadenza e revoca | API comunque spenta finché non serve |
| ⬜ | Tracciato del flusso regionale delle presenze | quando l'ATS indica il formato |
| ⬜ | Fatturazione elettronica delle rette (SDI) | solo se le rette vanno fatturate dal sistema; altrimenti export al gestionale |
| ✅ | Anagrafica dei farmaci da fonte ufficiale | elenco open data AIFA (CC BY 4.0) caricato dalla struttura; le interazioni restano quelle validate dal medico |
| 🟡 | Codici a barre alla somministrazione | controllo della confezione nel giro farmaci (lettore o fotocamera); braccialetto dell'ospite da fare |
| ✅ | Pacchetto «pronto per l'ispezione» | report unico per la vigilanza ATS |
| ⬜ | Conservazione a norma | invio dei fascicoli chiusi a un conservatore accreditato |
| ⬜ | Firma di più documenti con un'unica autorizzazione | firma massiva per i medici |
| 🟡 | FASAS Signer per Android | **congelato**: APK di prova compilabile a mano da GitHub, da collaudare con una CIE reale solo se la struttura attiva la firma con CIE |
| 🟡 | FASAS Signer per iPhone | **congelato**: app SwiftUI compilabile a mano; per installarla servono l'Apple Developer Program (a pagamento) e TestFlight, poi il collaudo con una CIE reale |
| ⬜ | Pacchetti installabili del FASAS Signer | eseguibili firmati per Windows (Authenticode) e macOS (notarizzazione Apple) |

## Fase 3 – Futuro

| | Attività | Note |
|---|---|---|
| 🟡 | Più comunità | resta predisposto (decisione: va bene così per ora) |
| ⬜ | Integrazioni regionali | Fascicolo Sanitario Elettronico, ricetta dematerializzata |
| ⬜ | Area familiari | comunicazioni e visite, con le tutele di riservatezza |

## Backup fuori sede – decisione

Ogni notte il FASAS fa un backup **cifrato** (AES-256-GCM, chiave solo della struttura), lo verifica e lo copia
fuori sede su **Backblaze B2** (regione UE, blocco delle modifiche per 14 giorni, piano gratuito fino a 10 GB): il
fornitore vede solo dati cifrati. Ogni mese una copia su **disco USB** custodito in un altro luogo
(`scripts/copia_backup_usb.sh`). Ogni tre mesi la **prova di ripristino** automatica con verbale.
Chiave `FASAS_BACKUP_KEY` in due luoghi: gestore password della direzione e busta sigillata in cassaforte.
Dettagli: [INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md) e [BACKUP.md](BACKUP.md).
