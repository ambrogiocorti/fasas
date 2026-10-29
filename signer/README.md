# FASAS Signer Desktop

Programma per Windows, macOS e Linux che firma i documenti del FASAS con la **CIE** appoggiata a un lettore NFC,
usando il **Software CIE** del Ministero dell'Interno (modulo PKCS#11). Guida completa: [docs/FIRMA_CIE.md](../docs/FIRMA_CIE.md).

> Provato con un modulo PKCS#11 reale (SoftHSM2) e certificati di prova su Linux. **Non ancora collaudato con
> una CIE reale** né su Windows o macOS.

## Requisiti

- Python 3.11 o successivo con tkinter (incluso negli installer di python.org per Windows e macOS; su
  Debian/Ubuntu: `sudo apt install python3-tk`).
- Software CIE installato e carta **abbinata** dall'app «CIE ID».
- Lettore NFC contactless collegato (su Linux anche `pcscd` attivo).

## Installazione

```bash
python -m venv fasas-signer
```

```bash
fasas-signer/bin/pip install -r requirements.txt
```

Su Windows il secondo comando è `fasas-signer\Scripts\pip install -r requirements.txt`.

## Uso

Finestra (uso normale):

```bash
fasas-signer/bin/python -m fasas_signer
```

Al primo avvio premere «Abbina al FASAS…» e inserire l'indirizzo del FASAS e il codice mostrato in
Impostazioni › Firma digitale. Poi il Signer resta in attesa: quando dal FASAS si avvia una firma compare la
richiesta con il **codice di controllo**, che deve coincidere con quello della pagina.

Altri comandi:

```bash
fasas-signer/bin/python -m fasas_signer diagnostica
```

```bash
fasas-signer/bin/python -m fasas_signer abbina --server https://fasas.esempio.it/ --codice ABCD-EFGH --nome "PC ambulatorio"
```

```bash
fasas-signer/bin/python -m fasas_signer console
```

Se il Software CIE è in un percorso diverso da quello standard, aggiungere `--libreria PERCORSO` (es.
`--libreria /usr/local/lib/libcie-pkcs11.so`): il percorso viene ricordato.

| Sistema | Modulo PKCS#11 cercato |
|---|---|
| Windows | `C:\Windows\System32\CIEPKI.dll` |
| macOS | `/Library/ipzs/libcie-pkcs11.dylib`, `/usr/local/lib/libcie-pkcs11.dylib` (con la versione da App Store il percorso va verificato) |
| Linux | `/usr/local/lib/libcie-pkcs11.so`, `/usr/lib/libcie-pkcs11.so`, `/usr/lib/x86_64-linux-gnu/libcie-pkcs11.so` |

## Sicurezza

- Il PIN (le ultime 4 cifre dopo l'abbinamento della carta) si digita solo qui e va solo al modulo PKCS#11;
  non viene salvato, inviato al server o scritto nei log.
- Il Signer non apre porte sul computer: è lui a contattare il FASAS in HTTPS, con verifica del certificato.
- La configurazione (indirizzo, token del dispositivo, percorso del modulo) è in `config.json` nella cartella
  dell'utente (`%APPDATA%\FASAS Signer` su Windows, `~/Library/Application Support/FASAS Signer` su macOS,
  `~/.config/FASAS Signer` su Linux), leggibile solo dall'utente. Il token da solo non permette di firmare
  (servono carta e PIN); se il computer viene perso, revocarlo dal FASAS.

## Pacchetto eseguibile

Per distribuire il Signer senza installare Python si può usare PyInstaller sul sistema di destinazione:

```bash
fasas-signer/bin/pip install pyinstaller
```

```bash
fasas-signer/bin/pyinstaller --name "FASAS Signer" --windowed --collect-all certifi fasas_signer/__main__.py
```

In produzione l'eseguibile va firmato (Authenticode su Windows, notarizzazione Apple su macOS) per evitare gli
avvisi del sistema. Il pacchetto non è stato generato né provato in questo ambiente.

## Test

I test sono nel progetto principale e usano SoftHSM2 come modulo PKCS#11 reale:

```bash
python manage.py test fasas.tests.test_cie_signer_pkcs11
```
