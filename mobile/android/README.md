# FASAS Signer per Android – prototipo

> **Prototipo non collaudato con una CIE reale.** L'APK non è stato generato in questo ambiente (l'SDK Android
> non è scaricabile qui). Non usarlo sui documenti degli ospiti prima del collaudo.

## Perché un'app

Il browser non può firmare con la CIE: Web NFC (Chrome) gestisce solo etichette NDEF e non invia comandi
ISO 7816 al chip. Un'app nativa usa `IsoDep` e il protocollo **IAS** della CIE: Diffie-Hellman, autenticazione
del dispositivo (DAPP), canale sicuro, `VERIFY PIN` con il PIN completo (8 cifre), `MSE SET` +
`INTERNAL AUTHENTICATE` sul DigestInfo SHA-256 (la carta applica il padding PKCS#1 v1.5, come nel middleware
ufficiale). Le stesse API del FASAS usate dal Signer per computer.

## Struttura

| Modulo | Contenuto | Stato |
|---|---|---|
| `signer-core` | client delle API FASAS e flusso di firma (Kotlin puro) | compilato e **collaudato contro un FASAS in esecuzione** con una chiave di prova al posto della carta (PIN errato poi corretto, seconda firma valida sullo stesso PDF) |
| `app` | attività Android: abbinamento, conferma con codice di controllo, PIN, lettura NFC (`enableReaderMode`), esito | il codice Kotlin compila contro le API di Android 14 (jar `android-all`); manifest, risorse e APK non verificati |
| libreria IAS | `it.ipzs.cieidsdk.nfc.Ias` di [pagopa/io-cie-android-sdk](https://github.com/pagopa/io-cie-android-sdk) (MIT), usata in produzione per l'accesso con CIE | scaricata da `scripts/fetch_ias.sh` a un commit fissato; non versionata qui. Il suo logger è sostituito da uno che non scrive nulla |

## Compilare (Android Studio)

1. `./scripts/fetch_ias.sh` (scarica la libreria IAS al commit indicato nello script).
2. Aprire la cartella `mobile/android` in Android Studio (con l'SDK Android 34): il modulo `app` viene incluso
   quando c'è `local.properties` o `ANDROID_HOME`.
3. Eseguire su un telefono con NFC; nel FASAS: Impostazioni › Firma digitale › Abbina un nuovo FASAS Signer.

Collaudo del modulo `signer-core` contro un FASAS (serve un server di sviluppo con una richiesta in attesa e
una chiave/certificato di prova):

```bash
FASAS_TEST_SERVER=http://127.0.0.1:8000/ FASAS_TEST_PAIRING_CODE=ABCD-EFGH FASAS_TEST_KEY=chiave.pk8 FASAS_TEST_CERT=cert.der gradle :signer-core:test
```

## Da fare prima dell'uso

- Collaudo con CIE reali su più telefoni (posizione dell'antenna, tempi della sessione NFC, carta allontanata).
- Conservazione del token del dispositivo con Android Keystore (ora in `SharedPreferences` private dell'app).
- Gestione dei tentativi PIN: la libreria restituisce i tentativi rimasti (`PinNotValidException.tentativi`).
- Distribuzione: APK firmato interno (gratuito) o Google Play (account sviluppatore, quota una tantum).
