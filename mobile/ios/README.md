# FASAS Signer per iPhone – studio e prototipo

> **Prototipo non compilato né collaudato**: richiede un Mac con Xcode, l'Apple Developer Program e un iPhone
> con NFC (iPhone 7 o successivi). Non va usato sui documenti degli ospiti prima del collaudo con una CIE reale.

## Fattibilità

- Safari e le PWA **non** possono usare la CIE: non hanno accesso all'NFC.
- Un'app nativa può dialogare con il chip con **Core NFC** (`NFCTagReaderSession`, polling ISO 14443, tag
  `NFCISO7816Tag`), dichiarando gli identificativi ISO 7816 della CIE e la capability «Near Field Communication
  Tag Reading».
- PagoPA pubblica [CieSDK](https://github.com/pagopa/cie-sdk-ios) (Swift, licenza MIT), usata per l'accesso con
  CIE: implementa canale sicuro, verifica del PIN (8 cifre), lettura del certificato e firma sul chip, ma non
  espone un metodo pubblico per firmare un dato arbitrario. La patch
  `patches/cie-sdk-ios-63d2195-performSignature.patch` (verificata con `git apply --check` sul commit
  `63d2195`) aggiunge `performSignature(withPin:prepare:)`: in un'unica sessione NFC apre il canale sicuro,
  verifica il PIN, legge il certificato, lo passa al FASAS e firma il DigestInfo restituito.

## File

| File | Contenuto |
|---|---|
| `FasasSigner/FasasAPI.swift` | client delle API FASAS (solo HTTPS) |
| `FasasSigner/CieSigner.swift` | flusso di firma con CieSDK (patch inclusa) |
| `FasasSigner/Entitlements.plist` | capability NFC (`TAG`) |
| `FasasSigner/Info-NFC.plist` | descrizione d'uso e identificativi ISO 7816 della CIE (ordine indicato da PagoPA) |

## Costi e distribuzione

- **Apple Developer Program**: quota annuale (99 USD/anno secondo il listino Apple; verificare l'importo in euro).
  Apple prevede un esonero dalla quota per enti non profit, istituti di istruzione e enti pubblici dei paesi
  ammessi: verificare se la comunità o l'ente gestore ne ha diritto.
- Distribuzione: TestFlight per il collaudo, poi App Store o distribuzione privata (app personalizzate tramite
  Apple Business Manager). Serve comunque un Mac per compilare.

## Da fare

1. Progetto Xcode con CieSDK (Swift Package o CocoaPods) e la patch.
2. Interfaccia (SwiftUI): abbinamento, attesa delle richieste, conferma con codice di controllo, PIN, esito.
3. Mappatura precisa degli errori di CieSDK sui codici del FASAS (PIN errato con tentativi rimasti, carta
   bloccata, sessione NFC interrotta) e token del dispositivo nel Portachiavi (Keychain).
4. Collaudo con CIE reali su più modelli di iPhone.
