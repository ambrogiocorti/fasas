# Firma digitale

FASAS Digitale firma i documenti sanitari in PDF (PAI, prescrizioni, relazioni, autorizzazioni alla contenzione)
nel formato **PAdES**: la firma è dentro il PDF e si verifica con qualunque software di verifica
(Adobe Reader, DiKe, Firma OK!, il validatore europeo DSS). Ogni firma crea una **nuova versione** del documento:
l'originale resta archiviato, e la firma è registrata nell'audit log.

## Quale firma serve

| Strumento | Valore legale | Quando usarlo |
|---|---|---|
| **Firma remota qualificata** (consigliata) | Firma elettronica qualificata (FEQ): equivale alla firma autografa (art. 25 Reg. UE 910/2014 eIDAS, art. 24 CAD) | Il medico ha un contratto di firma remota con un prestatore qualificato (QTSP) e firma con PIN + OTP dall'app o via SMS |
| **Firma con CIE** | Firma elettronica avanzata (FEA), mai qualificata | Il medico o il coordinatore firma con la propria CIE su un computer con lettore NFC e FASAS Signer – guida in [FIRMA_CIE.md](FIRMA_CIE.md) |
| Certificato personale in file (.p12) | Firma elettronica **non qualificata**: una chiave in un file non è in un dispositivo qualificato, anche se il certificato è di un prestatore | Prove, uso interno |
| Approvazioni interne (SOS, chiusura turno, PAI) | Non sono firme elettroniche avanzate né qualificate: tracciabilità nell'audit | Sempre attive |

Il FASAS registra per ogni firma il **valore giuridico** (`legal_level`): «qualificata» solo per la firma remota
con certificato che dichiara QcCompliance e QcSSCD e catena verificata con le CA configurate dall'amministratore;
altrimenti «non qualificata». Per i documenti sanitari che richiedono la firma del medico serve in pratica la
**firma remota qualificata**; dove basta una firma elettronica avanzata si può usare la **CIE**.

## Come funziona la firma remota

FASAS usa le **API CSC** (Cloud Signature Consortium, versione 1.0.4): lo standard europeo per la firma remota,
offerto da molti prestatori qualificati accanto alle loro API proprietarie. Il flusso:

1. il medico apre il documento e preme **Firma**;
2. se il prestatore manda l'OTP via SMS, preme **Invia OTP via SMS**; con l'app OTP il codice è già sul telefono;
3. inserisce **PIN** e **OTP** e conferma;
4. FASAS calcola l'**impronta** (hash SHA-256) del PDF e la invia al prestatore: **il documento non esce
   dal server**. Il prestatore la firma con la chiave del medico custodita nel suo HSM e restituisce la firma,
   che FASAS inserisce nel PDF.

Password del servizio, PIN e OTP **non vengono mai salvati**. Dopo l'invio dell'SMS la sessione con il prestatore
resta aperta per 5 minuti, cifrata, solo per completare quella firma. Se il prestatore lo richiede
(credenziali «SCAL 2»), l'autorizzazione vale solo per le impronte dei documenti da firmare.

## Configurazione (amministratore)

### 1. Scegliere il prestatore

Chiedete al prestatore qualificato (es. InfoCert, Namirial, Intesi Group, Aruba: verificate l'offerta attuale):

- **firma remota qualificata** per ciascun medico (certificato a nome del medico, con OTP);
- **accesso alle API CSC v1** per l'integrazione con un software di terzi: URL del servizio e modalità di accesso
  (utente e password del medico, oppure credenziali client OAuth2 della struttura);
- un ambiente di **prova** (sandbox), se disponibile;
- facoltativo ma consigliato: un servizio di **marca temporale** (TSA, RFC 3161) con le sue credenziali.

### 2. Impostare le variabili nel file `.env` del server

```ini
# Servizio CSC del prestatore
FASAS_CSC_SERVICE_URL=https://firma.prestatore.example     # la parte prima di /csc/v1/...
FASAS_CSC_PROVIDER_NAME=Nome del prestatore                # mostrato ai medici
FASAS_CSC_AUTH=basic                                       # basic | oauth2 | token
# Solo con FASAS_CSC_AUTH=oauth2 (credenziali della struttura):
FASAS_CSC_OAUTH_TOKEN_URL=https://firma.prestatore.example/oauth2/token
FASAS_CSC_CLIENT_ID=...
FASAS_CSC_CLIENT_SECRET=...

# Marca temporale e livello della firma
FASAS_SIGNATURE_TSA_URL=https://tsa.prestatore.example/tsa
FASAS_SIGNATURE_TSA_USER=...
FASAS_SIGNATURE_TSA_PASSWORD=...
FASAS_SIGNATURE_LEVEL=B-T          # B-B, B-T, B-LT, B-LTA
FASAS_SIGNATURE_TRUST_ROOTS=/opt/fasas/qtsp-ca.pem         # CA del prestatore (per B-LT e per la verifica)
```

Livelli PAdES:

| Livello | Contenuto | Note |
|---|---|---|
| B-B | firma | la data è quella dichiarata dal server |
| **B-T** | firma + marca temporale | **consigliato**: data certa opponibile a terzi |
| B-LT | + certificati e stato di revoca incorporati | verificabile anche dopo la scadenza del certificato |
| B-LTA | + marca temporale d'archivio | per la conservazione di lungo periodo |

Riavviate l'applicazione e controllate:

```bash
python manage.py fasas_firma_verifica
python manage.py fasas_firma_verifica --utente <utente del medico presso il prestatore>
```

Il comando mostra livello, marca temporale, raggiungibilità del servizio e, con `--utente`, le credenziali
di firma trovate e il tipo di sblocco (PIN, OTP via app o SMS).

Il server deve poter raggiungere in HTTPS il servizio del prestatore (il proxy di sistema `HTTPS_PROXY`, se c'è,
viene usato in automatico).

## Configurazione (medico, una volta sola)

1. **Impostazioni → Firma digitale** (anche dal cruscotto *Area medica* e da *Documenti da firmare*).
2. In **Firma remota qualificata** inserite utente e password ricevuti dal prestatore e premete
   **Collega la firma remota**. FASAS legge il certificato (titolare, emittente, validità) e il tipo di sblocco.
3. Se avete più firme presso lo stesso prestatore, indicate l'identificativo della credenziale da usare.

In alternativa si può caricare un certificato `.p12/.pfx`: viene cifrato sul server e la passphrase va digitata
a ogni firma.

## Firmare

1. Aprite il documento PDF nella cartella dell'ospite (o da **Documenti da firmare** nell'Area medica).
2. **Firma** → (se serve) **Invia OTP via SMS** → inserite PIN e OTP → spuntate la conferma → **Firma**.
3. Il documento ha ora una nuova versione «firmata»; **Verifica firme** mostra firmatario, integrità,
   marca temporale e, se sono configurate le CA in `FASAS_SIGNATURE_TRUST_ROOTS`, la catena di fiducia.

## Problemi frequenti

| Messaggio | Cosa fare |
|---|---|
| «Credenziali di accesso al servizio di firma non corrette» | utente o password del prestatore errati |
| «PIN non corretto» / «OTP non corretto o scaduto» | ripetere; dopo vari tentativi errati il prestatore può bloccare la firma |
| «richiede l'autorizzazione via browser (oauth2code)» | il prestatore usa un flusso non ancora supportato: chiedere l'abilitazione di PIN/OTP via API |
| «Il livello PAdES-B-T richiede una marca temporale» | configurare `FASAS_SIGNATURE_TSA_URL` o impostare `FASAS_SIGNATURE_LEVEL=B-B` |
| «Servizio di firma non raggiungibile» | rete o firewall del server; provare `fasas_firma_verifica` |

## Limiti attuali

- API CSC **v1.0.4**; la v2 non è ancora supportata (molti prestatori espongono entrambe).
- Il flusso «oauth2code» (autorizzazione della firma con reindirizzamento al sito del prestatore) non è supportato.
- Una firma per volta: la firma massiva di più documenti con una sola autorizzazione è una possibile evoluzione.
