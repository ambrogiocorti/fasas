# Roadmap

Stato al [29/10/2026]. ✅ fatto · 🟡 da decidere o da completare fuori dal software · ⬜ da fare

## Fase 1 – Prima di inserire dati reali

| | Attività | Note |
|---|---|---|
| ✅ | Importazione dal FASAS cartaceo | modello Excel con anteprima degli errori, scansioni abbinate all'ospite – [IMPORTAZIONE.md](IMPORTAZIONE.md) |
| ✅ | Firma digitale remota qualificata | API CSC, PIN + OTP, PAdES con marca temporale – [FIRMA_DIGITALE.md](FIRMA_DIGITALE.md). Serve il contratto con un prestatore e una prova nella sua sandbox |
| 🟡 | Firma elettronica avanzata con CIE (FASAS Sign) | server, interfaccia e FASAS Signer per computer pronti e provati con PKCS#11 reale (SoftHSM) – [FIRMA_CIE.md](FIRMA_CIE.md). **Da collaudare con una CIE reale** su Windows, macOS e Linux; CA della CIE da configurare; uso della FEA da validare con il consulente legale/DPO |
| ✅ | Lavoro senza rete e foglio di emergenza | [NOTIFICHE_E_SENZA_RETE.md](NOTIFICHE_E_SENZA_RETE.md) |
| 🟡 | Backup fuori sede | da scegliere tra le opzioni proposte (consigliata: object storage UE con blocco delle modifiche); poi integrazione e prova di ripristino |
| ⬜ | Autenticazione a due fattori | obbligatoria per amministratore, coordinatore, medico e accessi da fuori rete |
| ⬜ | Verifica notturna dell'audit log con risultato salvato | evita il ricalcolo all'apertura del pannello amministratore |
| 🟡 | GDPR: registro, DPIA, informative, nomine | bozze pronte in [gdpr/](gdpr/README.md), da completare con DPO/consulente |
| 🟡 | Requisiti FASAS regionali e conservazione | checklist per l'ATS in [gdpr/CHECKLIST_ATS.md](gdpr/CHECKLIST_ATS.md) |
| 🟡 | Validazione clinica di protocolli e interazioni | a cura del medico / direttore sanitario |
| 🟡 | Prova sul campo | 2–4 settimane con 2–3 operatori, accanto alla carta |

## Fase 2 – Miglioramenti di grande utilità

| | Attività | Note |
|---|---|---|
| ✅ | Notifiche push sul telefono | senza dati sanitari sulla schermata di blocco |
| ✅ | Presenze per la rendicontazione, rette, prospetti, incassi | [PRESENZE_E_RETTE.md](PRESENZE_E_RETTE.md); ruolo Amministrativo |
| ✅ | Pianificazione mensile dei turni, ferie, cambi turno | [TURNI_DEL_PERSONALE.md](TURNI_DEL_PERSONALE.md) |
| ⬜ | Tracciato del flusso regionale delle presenze | quando l'ATS indica il formato |
| ⬜ | Fatturazione elettronica delle rette (SDI) | solo se le rette vanno fatturate dal sistema; altrimenti export al gestionale |
| ⬜ | Banca dati dei farmaci | anagrafica e interazioni da fonte ufficiale/commerciale |
| ⬜ | Codici a barre / QR alla somministrazione | braccialetto ospite + confezione |
| ⬜ | Pacchetto «pronto per l'ispezione» | report unico per la vigilanza ATS |
| ⬜ | Conservazione a norma | invio dei fascicoli chiusi a un conservatore accreditato |
| ⬜ | Firma di più documenti con un'unica autorizzazione | firma massiva per i medici |
| ⬜ | FASAS Signer per Android | prototipo: protocollo collaudato contro il server, NFC con libreria IAS di PagoPA/IPZS; da compilare con Android Studio e collaudare con una CIE reale |
| ⬜ | FASAS Signer per iPhone | studio e prototipo Core NFC (CieSDK di PagoPA + patch per la firma); serve un Mac, l'Apple Developer Program e il collaudo con una CIE reale |
| ⬜ | Pacchetti installabili del FASAS Signer | eseguibili firmati per Windows (Authenticode) e macOS (notarizzazione Apple) |

## Fase 3 – Futuro

| | Attività | Note |
|---|---|---|
| 🟡 | Più comunità | resta predisposto (decisione: va bene così per ora) |
| ⬜ | Integrazioni regionali | Fascicolo Sanitario Elettronico, ricetta dematerializzata |
| ⬜ | Area familiari | comunicazioni e visite, con le tutele di riservatezza |

## Backup fuori sede – opzioni da valutare

Il sistema fa già ogni notte un backup **cifrato** (AES-256-GCM, chiave solo della struttura) con verifica di
integrità, ma oggi resta sullo stesso server. Opzioni per la seconda copia:

| Opzione | Pro | Contro | Costo indicativo |
|---|---|---|---|
| **A. Object storage S3 in UE con blocco delle modifiche (Object Lock)** – es. provider con data center in Italia o UE | copia automatica ogni notte, immutabile per N giorni (protegge anche dal ransomware), il fornitore vede solo dati cifrati | serve contratto art. 28 e scelta del fornitore | pochi euro al mese per decine di GB |
| B. Backup gestiti del database (es. Supabase Pro, eventuale ripristino a un istante preciso) | nessun lavoro, ripristino rapido del database | copre solo il database, non i documenti; stesso fornitore della produzione | incluso nel piano a pagamento |
| C. NAS in struttura che scarica i backup | ripristino veloce in locale, nessun canone | rischi fisici (furto, incendio), da proteggere dal ransomware, manutenzione | acquisto del NAS |
| D. Disco esterno mensile in cassaforte | copia offline, semplicissima | manuale, si dimentica, dati fino a un mese vecchi | trascurabile |

**Proposta**: A come copia principale (ogni notte, conservazione 30 giornalieri + 12 mensili, blocco 30 giorni),
B se il database è su Supabase con piano a pagamento, D come ulteriore copia trimestrale. In ogni caso: chiave
`FASAS_BACKUP_KEY` custodita in due luoghi (gestore password della direzione e busta sigillata in cassaforte)
e **prova di ripristino ogni tre mesi** con verbale.
