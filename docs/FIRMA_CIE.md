# Firma con CIE (FASAS Sign)

Il medico o il coordinatore firma un documento PDF del FASAS appoggiando la propria **Carta d'Identità
Elettronica** al lettore NFC del computer. Il risultato è un PDF firmato in formato **PAdES**, archiviato come
nuova versione del documento, verificabile dentro e fuori dal FASAS.

> **Stato al 29/10/2026.** Server, interfaccia web e FASAS Signer per computer sono completi e provati con un
> modulo PKCS#11 reale (SoftHSM2) e con certificati di prova. **Nessuna piattaforma è stata ancora collaudata
> con una CIE reale**: finché il collaudo non è fatto, la firma con CIE non va usata sui documenti degli ospiti.
> Le app per telefono sono prototipi (vedi [più avanti](#telefoni-android-e-iphone)).

## 1. Valore giuridico

- È una **firma elettronica avanzata (FEA)**. Il manuale ufficiale del Software CIE (Ministero dell'Interno /
  IPZS, versione Linux, cap. «Funzionalità di Firma Elettronica Avanzata con la CIE») dice: *«La firma
  elettronica calcolata con la Carta D'Identità Elettronica è a tutti gli effetti una Firma Elettronica
  Avanzata, disciplinata all'interno del DPCM 22/02/2013, articolo 61.»*
- **Non è mai una firma qualificata (FEQ)**: il FASAS la registra sempre come «Firma elettronica avanzata»
  (`legal_level = fea`) e così la mostra nel documento e nelle impostazioni.
- **Da validare prima dell'uso reale.** Gli articoli 55–61 del DPCM 22/02/2013 fissano requisiti per le soluzioni
  di FEA (identificazione del firmatario, informativa, conservazione delle evidenze, ambito d'uso). Il consulente
  legale / DPO deve confermare per quali documenti della comunità la FEA con CIE è sufficiente e quali
  adempimenti documentare. Dove serve la FEQ (equivalente alla firma autografa) si usa la firma remota del
  prestatore qualificato ([FIRMA_DIGITALE.md](FIRMA_DIGITALE.md)).

| Modalità nel FASAS | Valore giuridico | Dove resta la chiave |
|---|---|---|
| Firma con CIE | Firma elettronica avanzata | nel chip della CIE |
| Firma remota del prestatore (QTSP) | Qualificata solo se il certificato lo dichiara (QcCompliance + QcSSCD) e la catena è verificata | nel dispositivo sicuro del prestatore |
| Certificato personale (.p12) | Non qualificata | in un file cifrato sul server |
| Approvazioni interne (SOS, chiusura turno, PAI) | Non è una firma elettronica avanzata né qualificata | nessuna chiave: utente e ora nell'audit |

## 2. Come funziona

```
 Browser del medico (FASAS)          Server FASAS                     Computer con lettore NFC
 ───────────────────────────         ────────────────────────         ──────────────────────────────
 Anteprima completa del PDF
 «Avvia la firma con CIE»  ───────►  richiesta: versione bloccata,
                                     codice di controllo, scadenza
                                     (5 min), nonce               ◄── FASAS Signer chiede (in uscita,
                                                                      HTTPS) le richieste in attesa
 «In attesa della CIE»                                                mostra titolo, versione, impronta e
                                                                      CODICE DI CONTROLLO → «Firma con CIE»
 «Carta rilevata»                    riceve il certificato        ◄── legge il certificato (senza PIN)
                                     · CF = CF dell'utente?
                                     · CA della CIE? revoca?
                                     · prepara il PDF (pyHanko)  ───► attributi firmati + DigestInfo
 «Autorizzazione richiesta»                                           PIN digitato QUI (ultime 4 cifre)
 «Firma in corso»                                                     la carta firma (PKCS#11, Software CIE)
 «Verifica della firma»              verifica RSA del valore,     ◄── solo il valore di firma
                                     inserisce la busta CMS, verifica
                                     integrità/copertura/catena
 «Documento firmato correttamente»   nuova versione firmata + audit
```

- **La chiave privata non esce mai dalla carta**: il FASAS Signer chiede alla carta di firmare tramite il modulo
  PKCS#11 del Software CIE (`CKM_SHA256_RSA_PKCS`, oppure `CKM_RSA_PKCS` sul DigestInfo). Abbiamo verificato
  nel sorgente ufficiale del middleware (repository `italia/cie-middleware-*`, licenza BSD-3) che in entrambi i
  casi la carta riceve il DigestInfo SHA-256 e applica da sé il padding PKCS#1 v1.5.
- **Il PIN non arriva mai al server**: si digita nel FASAS Signer e va solo al modulo PKCS#11 e alla carta. Sul
  computer, dopo l'abbinamento della carta nell'app «CIE ID», servono le **ultime 4 cifre**; sul telefono il PIN
  completo di 8 cifre. Le API del FASAS non hanno un campo per il PIN.
- **Il firmatario è l'utente collegato**: il codice fiscale nel certificato della carta (nella CIE è nel CN,
  come lo leggono gli SDK di PagoPA) deve coincidere con quello del profilo FASAS. Altrimenti la firma è
  rifiutata e il tentativo registrato nell'audit come «Tentativo non autorizzato».
- **Il documento firmato è quello mostrato**: la versione viene bloccata alla conferma (nessuna nuova versione,
  nessuna seconda richiesta), il server conserva l'impronta SHA-256, controlla che il PDF firmato inizi con il
  documento originale invariato e che la firma copra l'intero file. Il **codice di controllo** (es. `K7QM-3HXZ`)
  compare sia nella pagina del FASAS sia nel Signer: si firma solo se coincidono.
- **Firme multiple**: ogni firma è una revisione incrementale (campi `FirmaFASAS1`, `FirmaFASAS2`, …): le firme
  precedenti restano valide.
- **Marca temporale**: solo se è configurata una TSA reale (`FASAS_SIGNATURE_TSA_URL`): PAdES-B-T. Senza TSA:
  PAdES-B-B. Nessuna marca temporale fittizia.

### Stati della richiesta

| Stato | Documento | Significato |
|---|---|---|
| In attesa della CIE | in attesa di firma (bloccato) | richiesta creata; il Signer deve prenderla in carico e la carta va appoggiata |
| Carta rilevata | in attesa di firma | certificato letto e in controllo |
| Autorizzazione richiesta | in attesa di firma | PDF preparato; il Signer chiede il PIN |
| Firma in corso | firma in corso | PIN verificato, la carta sta firmando |
| Verifica della firma | firma in corso | il server verifica e archivia |
| Documento firmato correttamente | firmato | nuova versione firmata archiviata |
| Firma non riuscita / Annullata / Scaduta | torna modificabile | motivo mostrato; «Riprova» crea una **nuova** richiesta (nuovo codice e nonce) |

### Sicurezza

| Rischio | Contromisura |
|---|---|
| Una pagina web pilota il Signer (CSRF, richieste cross-origin) | il Signer non apre porte sul computer: contatta lui il server in uscita |
| Furto del token del dispositivo | sul server solo l'impronta SHA-256; il token da solo non basta: servono la carta e il PIN; revoca immediata da Impostazioni o dall'amministratore (Sistema › Dispositivi di firma) |
| Ripetizione di una risposta (replay) | nonce diverso a ogni passo, accettato una volta sola; richieste che scadono; valore di firma accettato una sola volta |
| Accesso alle richieste altrui (IDOR) | ogni richiesta è visibile e utilizzabile solo dal firmatario e dal dispositivo che l'ha presa in carico; i tentativi diversi finiscono nell'audit |
| Carta di un'altra persona | confronto del codice fiscale del certificato con il profilo dell'utente |
| Certificato falso, scaduto o revocato | catena verso le CA della CIE configurate, date di validità, revoca (OCSP/CRL) quando raggiungibile |
| Documento cambiato durante la firma | versione bloccata, impronta controllata prima e dopo, PDF firmato = originale + revisione incrementale |
| Dati sanitari nei log | il server registra solo codici di esito; il dispositivo può riportare solo codici d'errore noti, mai testo libero; il Signer non scrive titoli, PIN o certificati nei log; il PDF preparato è cifrato e cancellato a fine richiesta |
| Connessione in chiaro | il Signer rifiuta HTTP verso server non locali; le API rispondono 403 senza HTTPS (salvo `FASAS_CIE_ALLOW_HTTP` in sviluppo) |
| Abbinamento indovinato | codice monouso di 8 caratteri, valido 10 minuti; dopo 10 tentativi falliti per IP l'abbinamento si blocca per 10 minuti |
| Database (Supabase) | le nuove tabelle ricevono automaticamente RLS e la revoca dei privilegi pubblici come tutte le altre |
| Manomissione dell'audit | catena di impronte SHA-256 e trigger append-only su PostgreSQL: le manomissioni si **rilevano**. Non è un registro legalmente immodificabile |

## 3. Cosa serve

| Elemento | Dove | Costo |
|---|---|---|
| CIE del firmatario con PIN e PUK | – | – |
| Lettore NFC contactless (ISO 14443) compatibile con la CIE | un lettore per ogni postazione di firma | indicativamente 20–50 € l'uno (stima, da verificare con i fornitori) |
| Software CIE del Ministero dell'Interno | ogni computer di firma | gratuito |
| FASAS Signer | ogni computer di firma | gratuito (questo progetto) |
| Certificati delle CA della CIE | server FASAS | gratuiti |
| Marca temporale (facoltativa) | server FASAS | servizio a pagamento di un prestatore (già previsto in [FIRMA_DIGITALE.md](FIRMA_DIGITALE.md)) |
| Firma del codice del Signer (consigliata) | distribuzione | Windows: certificato Authenticode (centinaia di €/anno); macOS: Apple Developer Program |

Nessun servizio a pagamento è stato attivato.

## 4. Configurazione del server (amministratore)

Variabili d'ambiente (vedi `config/settings.py`):

| Variabile | Valore |
|---|---|
| `FASAS_CIE_ENABLED` | `1` (predefinito) |
| `FASAS_CIE_TRUST_ROOTS` | percorso di un file PEM con i certificati radice della CIE. **Obbligatorio**: senza, la firma con CIE non parte |
| `FASAS_CIE_INTERMEDIATES` | PEM con le CA intermedie, se non sono già nella firma |
| `FASAS_CIE_REVOCATION` | `soft-fail` (predefinito: verifica la revoca se OCSP/CRL sono raggiungibili), `hard-fail` (rifiuta se non verificabile), `off` (solo prove) |
| `FASAS_CIE_TIMESTAMP` | `1`: marca temporale se è configurata la TSA |
| `FASAS_CIE_REQUEST_MINUTES` | durata massima di una richiesta (5) |
| `FASAS_CIE_PAIRING_MINUTES` | validità del codice di abbinamento (10) |

Le **CA della CIE** si scaricano dal sito ufficiale della CIE (Ministero dell'Interno). Prima di configurarle
confrontate le impronte con quelle pubblicate dal Ministero: sono il punto su cui si regge la verifica.
Il server deve poter raggiungere i servizi OCSP/CRL indicati nei certificati per il controllo di revoca.

Permessi: «Firma con CIE» è concesso a **medico** e **coordinatore** (`signatures.sign_with_cie`); l'amministratore
può solo revocare i dispositivi (`signatures.manage_signer_devices`). Nel profilo di ogni firmatario va inserito
il **codice fiscale**.

## 5. Installazione del FASAS Signer sul computer

1. Installare il **Software CIE**: Windows (`CIEPKI.dll` in System32), macOS (pacchetto con
   `/Library/ipzs/libcie-pkcs11.dylib`, oppure «Software CIE» dal Mac App Store), Linux (pacchetto .deb/.rpm con
   `/usr/local/lib/libcie-pkcs11.so`, più `pcscd`). Percorsi presi dai manuali ufficiali.
2. Collegare il lettore, aprire l'app **CIE ID**, appoggiare la carta e fare l'**abbinamento** (chiede le 8 cifre
   del PIN una sola volta). Senza abbinamento il Software CIE non espone il certificato e il Signer lo segnala.
3. Installare il FASAS Signer: istruzioni in [signer/README.md](../signer/README.md).
4. Nel FASAS: **Impostazioni › Firma digitale › Abbina un nuovo FASAS Signer** → compare un codice; nel Signer
   «Abbina al FASAS…», inserire indirizzo del FASAS e codice.
5. Sempre in Impostazioni: **Prova la firma con CIE** firma un PDF di prova senza dati sanitari e mostra l'esito
   della verifica (catena, integrità) prima di usare la firma sui documenti.

## 6. Uso

1. Nel documento (o in «Documenti da firmare») premere **Firma con CIE**: si apre l'anteprima completa del PDF.
2. Spuntare «Ho letto il documento…» e **Avvia la firma con CIE**: la versione si blocca.
3. Sul FASAS Signer controllare titolo, versione e **codice di controllo**, poi «Firma con CIE».
4. Appoggiare la CIE sul lettore e digitare le ultime 4 cifre del PIN.
5. La pagina del FASAS segue gli stati fino a «Documento firmato correttamente»; il documento ha una nuova
   versione con l'indicazione «Firma elettronica avanzata con CIE». In caso di errore: **Riprova**.

PIN errato: il Signer lo richiede e la pagina mostra i tentativi rimasti quando il modulo li comunica; dopo
3 errori il PIN si blocca e va sbloccato con il PUK dall'app CIE ID.

## 7. Verifica e conservazione

- Nel FASAS: **Verifica firme** sulla versione firmata (integrità, validità, catena verso le CA configurate,
  copertura del documento, valore giuridico).
- Fuori dal FASAS: app **CIE ID** («Firma elettronica › Verifica»), validatore europeo DSS, Adobe Reader (che
  mostra la firma come non attendibile finché la CA della CIE non è tra quelle di fiducia).
- Il livello prodotto è PAdES-B-B o B-T. La validazione a lungo termine (B-LT/B-LTA con i dati di revoca nel
  documento) **non è implementata** per la CIE: per la conservazione a lungo termine i documenti vanno affidati
  alla conservazione a norma (vedi la roadmap).

## 8. Telefoni (Android e iPhone)

- **Il browser non basta.** Web NFC (Chrome su Android) legge solo etichette NDEF e non può inviare i comandi
  ISO 7816 (APDU) al chip della CIE; Safari e le PWA su iPhone non hanno accesso all'NFC. Serve un'app nativa.
- **Android** – prototipo in [mobile/android](../mobile/android/README.md): il protocollo verso il FASAS e il
  flusso di firma (Kotlin) sono stati **collaudati contro il server** con una chiave di prova; l'app usa NFC
  IsoDep e la libreria IAS open source (MIT) di PagoPA/IPZS già usata per l'accesso con CIE, scaricata a una
  versione fissata. Il codice compila contro le API di Android 14, ma l'APK non è stato generato (SDK Android
  non disponibile qui) e **non è collaudato con una CIE reale**. Distribuzione: APK interno (gratuito) o
  Google Play (account sviluppatore, quota una tantum).
- **iPhone** – studio e prototipo in [mobile/ios](../mobile/ios/README.md): Core NFC (`NFCTagReaderSession`,
  tag ISO 7816) con la libreria CieSDK di PagoPA (MIT) più una piccola patch che aggiunge la firma del DigestInfo.
  Servono un Mac con Xcode, l'**Apple Developer Program** (quota annuale; esiste un esonero per enti non profit,
  istituti scolastici ed enti pubblici dei paesi ammessi: da verificare), la capability «NFC Tag Reading» e gli
  identificativi ISO 7816 della CIE nell'Info.plist. **Non compilato né collaudato.**

## 9. Prove eseguite

Automatiche (`python manage.py test fasas.tests.test_cie_signature fasas.tests.test_cie_signer_pkcs11`):

1. firma riuscita: nuova versione, FEA, PAdES verificabile, originale intatto, PDF preparato cancellato;
2. meccanismo alternativo (`CKM_RSA_PKCS` sul DigestInfo);
3. firme multiple: la seconda non invalida la prima;
4. carta di un'altra persona rifiutata e registrata come tentativo non autorizzato;
5. certificato scaduto rifiutato;
6. certificato non emesso dalla CA configurata rifiutato;
7. valore di firma che non corrisponde al documento rifiutato;
8. replay: nonce già usato rifiutato, anche a firma conclusa;
9. accesso di altri utenti o di un altro dispositivo (IDOR) negato e registrato;
10. versione bloccata durante la firma;
11. nessuna richiesta duplicata;
12. scadenza della richiesta;
13. annullamento e nuovo tentativo senza riuso;
14. errori del dispositivo: carta assente, PIN errato con tentativi, PIN bloccato, codici sconosciuti;
15. abbinamento monouso, revoca del dispositivo, limite dei tentativi;
16. prova di funzionamento con PDF senza dati sanitari;
17. HTTPS obbligatorio e firma bloccata senza le CA della CIE;
18. nessun PIN né contenuto del documento nei log e nell'audit;
19. manomissione del PDF firmato rilevata; pagina delle impostazioni con le quattro modalità; revoca da
    amministratore; stato dei componenti; zeri di riempimento del certificato letto dal chip;
20. **FASAS Signer con PKCS#11 reale (SoftHSM2)** contro il server in ascolto: chiave generata nel token,
    PIN errato poi corretto, firma verificata; rifiuto dell'utente, annullamento del PIN, middleware assente,
    carta assente o allontanata, PIN bloccato.

Manuali in questo ambiente (Linux, Xvfb): finestra del FASAS Signer con SoftHSM e pagina del FASAS in Chromium,
dall'anteprima del PDF fino a «Documento firmato correttamente» passando per un PIN errato; flusso Android
(Kotlin) contro il FASAS con chiave di prova: seconda firma valida sullo stesso PDF.

**Non verificato**: qualunque firma con una CIE reale; Software CIE reale su Windows, macOS e Linux; lettori NFC
reali; app Android su un telefono; app iOS; revoca OCSP/CRL con i servizi reali della CIE; marca temporale reale.

## 10. Prima dell'uso in produzione

1. Collaudo con una CIE reale e un lettore reale su ciascun sistema in uso (Windows, macOS, Linux): prova di
   funzionamento, firma di un documento di prova, verifica con l'app CIE ID e con il validatore DSS.
2. CA della CIE configurate con impronte verificate; servizi di revoca raggiungibili dal server.
3. Parere del consulente legale / DPO sull'uso della FEA con CIE e sugli adempimenti del DPCM 22/02/2013.
4. Codice fiscale in tutti i profili dei firmatari.
5. Distribuzione del Signer come eseguibile firmato e procedura di aggiornamento.
6. Revisione di sicurezza esterna (penetration test) di API e Signer.
