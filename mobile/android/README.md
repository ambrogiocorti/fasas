# FASAS Signer per Android

> **Prototipo non ancora collaudato con una CIE reale.** L'APK di prova è compilato automaticamente da GitHub;
> il primo uso con una CIE vera è il collaudo. Non usarlo sui documenti degli ospiti prima del collaudo.

## Perché un'app

Il browser non può firmare con la CIE: Web NFC (Chrome) gestisce solo etichette NDEF e non invia comandi
ISO 7816 al chip. Un'app nativa usa `IsoDep` e il protocollo **IAS** della CIE: Diffie-Hellman, autenticazione
del dispositivo (DAPP), canale sicuro, `VERIFY PIN` con il PIN completo (8 cifre), `MSE SET` +
`INTERNAL AUTHENTICATE` sul DigestInfo SHA-256 (la carta applica il padding PKCS#1 v1.5, come nel middleware
ufficiale). Le API del FASAS sono le stesse del Signer per computer.

## Provarla con il FASAS sul PC (stessa Wi-Fi)

1. **Scarica l'APK**: su GitHub, scheda *Actions* › workflow *App FASAS Signer* › ultima esecuzione riuscita ›
   *Artifacts* › `fasas-signer-android-prova` (serve essere collegati a GitHub). È un file zip: dentro c'è
   `app-debug.apk`.
2. **Installa** l'APK sul telefono (consenti l'installazione da questa origine quando Android lo chiede).
   L'app si chiama «FASAS Signer (prova)». Per aggiornarla a una nuova versione può servire disinstallarla prima.
3. **Avvia il FASAS raggiungibile dal telefono**: doppio clic su `avvia-telefono.bat` (al posto di `avvia.bat`).
   La finestra mostra l'indirizzo da usare, ad esempio `http://192.168.1.20:8000/`. Se Windows chiede di
   consentire l'accesso a Python, consentilo per le **reti private**. Telefono e PC devono essere sulla stessa Wi-Fi.
4. **Abbina**: nel FASAS sul PC entra come `medico`, Impostazioni › Firma digitale › «Abbina un nuovo FASAS
   Signer»; nell'app inserisci l'indirizzo del punto 3 e il codice, poi «Abbina».
5. **Firma**: dal PC avvia «Firma con CIE» su un documento (o «Prova la firma con CIE»). Sul telefono compare la
   richiesta: controlla che il codice di controllo coincida, «Firma con CIE», digita il **PIN completo di 8 cifre**,
   poi appoggia la CIE sul retro del telefono e tienila ferma fino all'esito. La pagina del FASAS segue gli stati.

Nel profilo FASAS del medico deve esserci il **tuo** codice fiscale; per firmare un documento vero (non la prova)
servono anche le CA della CIE configurate sul server (vedi [docs/FIRMA_CIE.md](../../docs/FIRMA_CIE.md)).

## Struttura

| Modulo | Contenuto | Stato |
|---|---|---|
| `signer-core` | client delle API FASAS e flusso di firma (Kotlin puro) | compilato e collaudato contro un FASAS in esecuzione con una chiave di prova al posto della carta |
| `app` | attività Android: abbinamento, conferma, PIN, lettura NFC (`enableReaderMode`), esito | APK di prova compilato nella CI; non collaudato con una CIE |
| libreria IAS | `it.ipzs.cieidsdk.nfc.Ias` di [pagopa/io-cie-android-sdk](https://github.com/pagopa/io-cie-android-sdk) (MIT), usata per l'accesso con CIE | scaricata da `scripts/fetch_ias.sh` a un commit fissato; non versionata qui. Il suo logger è sostituito da uno che non scrive nulla |

La **versione di prova** (build debug) accetta HTTP solo verso indirizzi IP della rete locale (10.x, 172.16–31.x,
192.168.x) e lo segnala con un riquadro rosso; la versione definitiva (release) accetta solo HTTPS.

## Compilare in proprio (Android Studio)

1. `./scripts/fetch_ias.sh`
2. Aprire `mobile/android` in Android Studio (SDK Android 34) ed eseguire su un telefono con NFC.

Collaudo del modulo `signer-core` contro un FASAS (server di sviluppo con una richiesta in attesa e una
chiave/certificato di prova):

```bash
FASAS_TEST_SERVER=http://127.0.0.1:8000/ FASAS_TEST_PAIRING_CODE=ABCD-EFGH FASAS_TEST_KEY=chiave.pk8 FASAS_TEST_CERT=cert.der gradle :signer-core:test
```

## Da fare prima dell'uso reale

- Collaudo con CIE reali su più telefoni (posizione dell'antenna, durata della sessione NFC, carta allontanata).
- Token del dispositivo protetto con Android Keystore (ora nelle preferenze private dell'app).
- FASAS pubblicato in HTTPS e APK firmato con una chiave della struttura (distribuzione interna gratuita, oppure
  Google Play con l'account sviluppatore, quota una tantum).
