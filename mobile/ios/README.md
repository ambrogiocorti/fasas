# FASAS Signer per iPhone

> **Prototipo: compila, ma non è ancora stato installato su un iPhone né collaudato con una CIE reale.**

## Come funziona

- Safari e le PWA **non** possono usare la CIE: non hanno accesso all'NFC. Serve un'app nativa.
- L'app usa **Core NFC** (`NFCTagReaderSession`, tag ISO 7816) tramite [CieSDK](https://github.com/pagopa/cie-sdk-ios)
  di PagoPA (Swift, licenza MIT), la stessa base usata per l'accesso con CIE. CieSDK non espone un metodo per
  firmare un dato qualsiasi: la patch `patches/cie-sdk-ios-63d2195-performSignature.patch` aggiunge
  `performSignature(withPin:prepare:)`, che in un'unica sessione NFC apre il canale sicuro, verifica il PIN,
  legge il certificato, lo passa al FASAS e firma il DigestInfo restituito.
- Flusso nell'app: richiesta dal FASAS → conferma con codice di controllo → PIN completo (8 cifre) → CIE sul
  retro dell'iPhone → esito. PIN errato: l'app lo richiede mostrando i tentativi rimasti. Il token del
  dispositivo è nel Portachiavi.

## Stato

| Cosa | Stato |
|---|---|
| Compilazione per iPhone (Xcode 16, iOS 15+) | ✅ nella CI su macOS, senza firma (workflow «App FASAS Signer») |
| Installazione su un iPhone | ⬜ serve la firma dell'app con un account Apple Developer |
| Collaudo con una CIE reale | ⬜ |

## Per installarla su un iPhone

1. **Apple Developer Program** (99 USD l'anno secondo il listino Apple; esiste un esonero dalla quota per enti
   non profit, istituti di istruzione ed enti pubblici dei paesi ammessi: da verificare). Con l'account gratuito
   («Personal Team») secondo i forum e le guide la lettura NFC non è disponibile.
2. Registrare l'identificativo `it.fasas.signer` con la capability «NFC Tag Reading».
3. Distribuzione con **TestFlight**: la CI su macOS può firmare e caricare l'app se le si forniscono come
   segreti di GitHub il certificato di distribuzione, il profilo e una chiave API di App Store Connect (non serve
   un Mac). I tester la installano con l'app TestFlight.

## Compilare in proprio (Mac con Xcode 16)

```bash
brew install xcodegen
```

```bash
./scripts/prepare.sh
```

Poi aprire `FasasSigner.xcodeproj`, scegliere il proprio team e avviare su un iPhone collegato.

La versione Debug è una **versione di prova**: accetta anche un FASAS sul PC della stessa rete Wi-Fi via HTTP
(solo indirizzi IP della rete locale) e lo segnala in rosso; la versione Release accetta solo HTTPS.
