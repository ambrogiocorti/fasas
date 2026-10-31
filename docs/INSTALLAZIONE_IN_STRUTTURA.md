# Installare il FASAS su un PC in struttura, raggiungibile in HTTPS gratis

Questa guida porta da zero a un FASAS funzionante su un PC della comunità, usabile dal personale in struttura e
da casa, con lucchetto HTTPS, verifica in due passaggi, backup cifrati fuori sede e su disco USB. Il software e i
servizi usati sono gratuiti; si spende solo per gli oggetti che mancano (vedi la lista della spesa).

- **Tempo**: mezza giornata la prima volta (gran parte è attesa di download e installazione).
- **Chi la fa**: una persona che sa entrare nel pannello del router e copiare comandi in un terminale.
  Ogni comando è scritto per intero; non serve saper programmare.
- **Cosa non copre**: gli adempimenti privacy e legali (DPIA, nomine, informative), elencati in fondo.

```
Telefoni e PC del personale, in struttura o da casa
        │  https://casarosa-fasas.duckdns.org   (DuckDNS: nome → IP pubblico della struttura)
        ▼
Internet ──► router della struttura ──(solo porte 80 e 443)──► PC FASAS: Ubuntu Server, disco cifrato
                                                                 Caddy: HTTPS, certificato gratuito
                                                                 FASAS: sito e job notturni
                                                                 PostgreSQL: dati; documenti cifrati
                                                                         │
                                         ┌───────────────────────────────┴───────────────┐
                                     ogni notte                                       ogni mese
                          Backblaze B2 (UE): backup cifrato,             disco USB: backup cifrati,
                          non cancellabile per 14 giorni                 tenuto in un altro luogo
```

---

## Lista degli oggetti da avere

| # | Oggetto | Requisiti | Note |
|---|---|---|---|
| 1 | **PC dedicato al FASAS** (il «server») | processore Intel o AMD a 64 bit; **8 GB di RAM** (minimo 4); **SSD da 256 GB** (minimo 128); porta di rete Ethernet; **chip TPM 2.0** (tutti i PC venduti con Windows 11 e quasi tutti quelli dal 2017); consumo basso | Solo per il FASAS: niente navigazione, posta o altri programmi. Un mini-PC consuma 10–15 W; un vecchio PC fisso 40–60 W (vedi «Costi che restano»). Va bene anche un portatile, collegato via cavo |
| 2 | **Router della struttura** con accesso al pannello | password di amministrazione; funzioni «inoltro porte» (port forwarding / virtual server / NAT) e «indirizzo fisso» (DHCP statico / prenotazione) | Serve un **IP pubblico vero** (passo 1): con alcune offerte l'operatore lo dà su richiesta |
| 3 | **Cavo di rete** dal router al server | categoria 6, lungo quanto serve | Il server non usa il Wi-Fi |
| 4 | **Chiavetta USB A** | almeno 8 GB | Per installare Ubuntu; dopo diventa la chiavetta della **busta delle chiavi** (passo 11) |
| 5 | **Disco esterno USB B** | 500 GB–1 TB | Copia mensile dei backup, da tenere in un altro luogo (passo 14) |
| 6 | Monitor e tastiera | qualsiasi | Solo per l'installazione; poi si lavora dal proprio PC |
| 7 | Un PC normale | Windows, Mac o Linux, con internet | Per scaricare Ubuntu, preparare la chiavetta e collegarsi al server |
| 8 | **Smartphone con app di autenticazione** | Google Authenticator, Microsoft Authenticator o FreeOTP (gratis) | Per amministratori, coordinatori, medici e per chi entra da fuori struttura |
| 9 | **Cassaforte o armadio chiuso a chiave** | — | Per chiavetta della busta, codici di recupero e foglio delle frasi segrete |
| 10 | **Locale chiuso per il server** | ventilato, vicino al router, con presa elettrica | Non in corridoio né in sala comune |
| 11 | **Gestore di password** | gratuito: Bitwarden (piano free) o KeePassXC | Per password e frasi segrete dei passi 4, 5, 7, 11 e 13 |
| 12 | **Account gratuiti** a nome della struttura | DuckDNS (passo 7), Backblaze B2 (passo 13), servizio di controllo (passo 16) | Usare un indirizzo email della struttura, non personale, e attivare la verifica in due passaggi anche lì |

Facoltativo ma consigliato: **gruppo di continuità (UPS)** per il server e il router, così un calo di corrente
non spegne nulla.

## Lista della spesa

Comprare **solo ciò che manca**. Prezzi indicativi del mercato italiano (ottobre 2026), da verificare al momento
dell'acquisto.

| Cosa | Quando serve | Prezzo indicativo |
|---|---|---|
| Mini-PC **ricondizionato** aziendale (formati «Tiny», «Mini», «Micro»), Intel di 8ª generazione o successiva, 8–16 GB, SSD 256 GB, con garanzia di 12 mesi | se non avete un PC da dedicare | 100–180 € |
| *oppure* mini-PC nuovo (es. Intel N100, 16 GB, SSD 512 GB) | come sopra | 150–220 € |
| Chiavetta USB 16–32 GB | se non ne avete una libera | 5–10 € |
| Disco esterno USB 1 TB | se non ne avete uno libero | 50–70 € |
| Cavo di rete cat. 6 (2–10 m) | se il router è lontano | 5–10 € |
| Gruppo di continuità «line-interactive» con AVR e porta USB, 650–900 VA (es. Eaton 5E Gen2 900 USB, versione con prese Schuko «5E900UD»; con più garanzie su Linux Eaton Ellipse PRO 650 DIN) | facoltativo, consigliato | 80–110 € (fino a circa 220 €) |

**Totale**: 0 € se avete già tutto; **circa 60–90 €** se avete già un PC; **circa 240–380 €** comprando anche
mini-PC ricondizionato e gruppo di continuità.

Software e servizi, tutti **0 €**: Ubuntu Server, Docker Engine, Caddy, PostgreSQL, certificati Let's Encrypt,
DuckDNS, Backblaze B2 fino a 10 GB, app di autenticazione, FASAS Digitale.

**Costi che restano** (non sono abbonamenti): la corrente del server, circa 25–35 € l'anno per un mini-PC acceso
sempre, 100–150 € per un vecchio PC fisso; il tempo di chi fa la manutenzione (passo 18).

---

## Parte A – Preparazione

### Passo 1. Tre controlli prima di comprare o iniziare (10 minuti)

**1a. La struttura ha un IP pubblico vero?** Senza, da fuori non si raggiunge il server.

1. Dal PC della struttura aprire <https://ifconfig.me>: è l'indirizzo con cui la struttura esce su internet.
2. Nel pannello del router (indirizzo e password sono di solito sull'etichetta sotto il router, es.
   `192.168.1.1`) cercare lo stato della connessione: «IP WAN» o «indirizzo IP pubblico».
3. Se i due numeri **coincidono**, va bene. Se sono diversi, oppure l'IP WAN inizia con `100.64`–`100.127`,
   `10.` o `192.168.`, la linea è dietro **CGNAT**: chiedere all'operatore un **IP pubblico** (alcuni lo danno
   gratis su richiesta, altri a pagamento). Non cambia nulla se l'IP pubblico è dinamico: ci pensa DuckDNS.

**1b. Il router permette l'inoltro delle porte?** Nel pannello cercare «Port forwarding», «Virtual server»,
«NAT/PAT» o «Inoltro porte». Se il router è dell'operatore e la voce non c'è, chiedere all'operatore di aprire
le porte TCP 80 e 443 verso un indirizzo della rete interna.

**1c. Il PC ha il TPM 2.0?** Su Windows: tasto Windows+R, scrivere `tpm.msc`, Invio: deve dire «Il TPM è pronto
per l'uso» e «Versione specifica: 2.0». In alternativa si controlla nel BIOS (passo 2).

> Se la linea è dietro CGNAT e l'operatore non dà un IP pubblico, questa guida non basta: servirebbe un
> certificato ottenuto con la verifica DNS di DuckDNS, che richiede una versione di Caddy con il modulo DuckDNS
> non inclusa ora nel FASAS. Non usare servizi «tunnel» che aprono il traffico HTTPS sui loro server: vedrebbero
> i dati sanitari in chiaro.

### Passo 2. Impostare il BIOS del server

Accendere il server e premere subito più volte il tasto del BIOS (di solito `F2`, `F10`, `F1` o `Canc`;
sui mini-PC Lenovo `F1`, HP `F10`, Dell `F2`). Poi:

1. **TPM**: attivo (voci «TPM», «Security Chip», «Intel PTT» o «AMD fTPM»).
2. **Secure Boot**: lasciarlo attivo.
3. **Ripristino dopo mancanza di corrente**: «Power On» (voci «After Power Loss», «AC Recovery», «Restore on AC
   Power Loss»). Così dopo un blackout il server si riaccende da solo.
4. **Avvio**: per ora mettere la chiavetta USB al primo posto.
5. Salvare e uscire (di solito `F10`).

La **password del BIOS** e lo spegnimento dell'avvio da USB si impostano al passo 5, a installazione finita.

### Passo 3. Preparare la chiavetta di installazione

Sul PC normale:

1. Scaricare **Ubuntu Server 24.04 LTS** da <https://ubuntu.com/download/server> (file
   `ubuntu-24.04.x-live-server-amd64.iso`, circa 3 GB). LTS significa aggiornamenti di sicurezza gratuiti fino
   al 2029.
2. Scaricare **balenaEtcher** (<https://etcher.balena.io>) o, su Windows, **Rufus** (<https://rufus.ie>), gratuiti.
3. Scegliere il file ISO e la chiavetta A, poi «Flash»/«Avvia». **Tutto il contenuto della chiavetta viene
   cancellato.**

---

## Parte B – Sistema operativo

### Passo 4. Installare Ubuntu Server con il disco cifrato

Collegare al server monitor, tastiera, cavo di rete e chiavetta A; accenderlo. Nel programma di installazione
(si va avanti con le frecce, `Invio` e `Tab`):

1. **Lingua**: Italiano se c'è, altrimenti English. **Tastiera**: Italian.
2. **Tipo di installazione**: «Ubuntu Server» (non «minimized»).
3. **Rete**: deve comparire un indirizzo tipo `192.168.1.50` sulla scheda via cavo (DHCP). Annotarlo.
4. **Proxy** vuoto, **mirror** quello proposto.
5. **Disco** («Guided storage configuration»): «Use an entire disk» sul disco interno, con
   **«Set up this disk as an LVM group»** e **«Encrypt the LVM group with LUKS»** spuntati.
   Scegliere una **frase di cifratura** lunga (almeno 5 parole a caso, es. `tavolo-nuvola-pera-treno-ottanta`),
   salvarla nel gestore di password e scriverla sul foglio che andrà in cassaforte.
   **Senza questa frase, se il TPM non sblocca il disco, i dati non si recuperano** (resterebbero i backup).
6. **Profilo**: nome, nome del server `fasas-server`, utente (es. `amministratore`) e una password robusta
   (nel gestore di password).
7. **Ubuntu Pro**: «Skip for now».
8. **SSH**: spuntare **«Install OpenSSH server»** (serve per lavorare dal proprio PC).
9. **Featured server snaps**: **non selezionare nulla** (in particolare non «docker»: si installa al passo 8).
10. A fine installazione «Reboot now», togliere la chiavetta quando richiesto.

Al riavvio il server chiede la frase di cifratura: scriverla e premere Invio. Poi entrare con utente e password.

Da qui si può lavorare dal proprio PC: su Windows aprire «PowerShell», su Mac «Terminale», e scrivere (con
l'indirizzo annotato al punto 3):

```bash
ssh amministratore@192.168.1.50
```

Aggiornare subito il sistema e riavviare:

```bash
sudo apt update && sudo apt full-upgrade -y && sudo reboot
```

### Passo 5. Sblocco automatico del disco con il TPM e protezione dell'avvio

Senza questo passo, dopo ogni blackout o riavvio qualcuno deve digitare la frase di cifratura sulla tastiera del
server. Con il TPM il disco si sblocca da solo **solo su quel PC e solo con il suo avvio originale**: un disco
estratto e letto altrove resta illeggibile.

**5a. Collegare il disco al TPM.**

```bash
sudo apt install -y clevis clevis-luks clevis-tpm2 clevis-initramfs
```

```bash
DISCO=$(sudo blkid -t TYPE=crypto_LUKS -o device | head -n 1); echo "$DISCO"
```

Deve stampare qualcosa come `/dev/nvme0n1p3` o `/dev/sda3`. Poi (chiede la frase di cifratura):

```bash
sudo clevis luks bind -d "$DISCO" tpm2 '{"pcr_bank":"sha256","pcr_ids":"7"}'
```

```bash
sudo update-initramfs -u -k all && sudo reboot
```

Al riavvio il server deve arrivare da solo alla richiesta di accesso, senza chiedere la frase. Se la chiede, la
frase funziona comunque: vedere «Problemi frequenti».

**5b. Chiudere le strade a chi ha il PC fra le mani.** Con lo sblocco automatico, chi ruba l'intero PC lo
vedrebbe avviarsi: queste tre misure impediscono di aggirare l'accesso.

1. **Password di GRUB** (impedisce di modificare l'avvio per entrare senza password). Prima si lascia libero
   l'avvio normale; il comando deve stampare `1`. **Se stampa `0`, fermarsi e saltare la password di GRUB**
   (passare al punto 2): con questa versione di Ubuntu la riga da modificare è diversa e il server si
   bloccherebbe all'avvio.

```bash
sudo sed -i 's/^CLASS="--class gnu-linux --class gnu --class os"$/CLASS="--class gnu-linux --class gnu --class os --unrestricted"/' /etc/grub.d/10_linux && grep -c -- --unrestricted /etc/grub.d/10_linux
```

   Poi scegliere la password di GRUB, salvarla nel gestore e scriverla quando richiesto:

```bash
read -rs -p "Password per GRUB: " PW; echo; HASH=$(printf '%s\n%s\n' "$PW" "$PW" | grub-mkpasswd-pbkdf2 | awk '/grub.pbkdf2/ {print $NF}'); unset PW; echo "${HASH:0:30}"
```

   Deve stampare un testo che inizia con `grub.pbkdf2.sha512`. Infine (stampa `fatto` solo se i due passaggi
   precedenti sono riusciti):

```bash
grep -q -- --unrestricted /etc/grub.d/10_linux && [ -n "$HASH" ] && printf 'set superusers="fasas"\npassword_pbkdf2 fasas %s\n' "$HASH" | sudo tee -a /etc/grub.d/40_custom > /dev/null && sudo mkdir -p /etc/default/grub.d && echo 'GRUB_DISABLE_RECOVERY="true"' | sudo tee /etc/default/grub.d/90-fasas.cfg > /dev/null && sudo update-grub && echo fatto
```

   L'avvio normale resta automatico; modificare l'avvio o usare la modalità di ripristino chiede la password.
2. **Password del BIOS** (supervisore/amministratore) nel BIOS, nel gestore di password e sul foglio in cassaforte.
3. Nel BIOS **togliere l'avvio da USB e da rete** (resta solo il disco interno).

Riavviare e controllare che il server arrivi da solo alla richiesta di accesso.

> **Alternativa più severa**: non fare il passo 5a e digitare la frase a ogni accensione. È più sicura contro il
> furto del PC, ma dopo un blackout o un riavvio per aggiornamenti il FASAS resta spento finché qualcuno con la
> frase non arriva al server: in quel caso al passo 9 rispondere «n» alla domanda sul riavvio automatico.

---

## Parte C – Rete

### Passo 6. Router: indirizzo fisso del server e inoltro delle porte

Nel pannello del router:

1. **Indirizzo fisso**: nella sezione DHCP («Prenotazione indirizzo», «DHCP statico», «Static lease») associare
   il server (si riconosce dal nome `fasas-server` o dall'indirizzo del passo 4) al suo indirizzo attuale, es.
   `192.168.1.50`.
2. **Inoltro porte**: due regole, protocollo **TCP**:
   - porta esterna **80** → `192.168.1.50` porta **80**
   - porta esterna **443** → `192.168.1.50` porta **443**
3. **Nient'altro**: non inoltrare mai la porta 22 (SSH) né altre porte.
4. Se c'è **UPnP**, disattivarlo; disattivare la **gestione remota del router** da internet; se la password del
   router è quella dell'etichetta, cambiarla (e salvarla nel gestore).

### Passo 7. Indirizzo gratuito con DuckDNS

1. Aprire <https://www.duckdns.org> ed entrare con un account **della struttura** (es. Google o GitHub,
   protetto da verifica in due passaggi: chi prende questo account può dirottare l'indirizzo).
2. In «sub domain» scrivere un nome (es. `casarosa-fasas`) e premere «add domain»: l'indirizzo sarà
   `casarosa-fasas.duckdns.org`. Il nome diventa pubblico: non metterci dati personali.
3. Tenere aperta la pagina: il **token** (in alto, una sequenza tipo `a1b2c3d4-…`) serve al passo 9.

L'aggiornamento dell'IP quando cambia lo installa lo script al passo 9 (controllo ogni 5 minuti).

---

## Parte D – FASAS

### Passo 8. Installare Docker e scaricare il FASAS

Dal terminale collegato al server:

```bash
sudo apt install -y docker.io docker-compose-v2 git
```

```bash
sudo git clone https://github.com/ambrogiocorti/fasas.git /opt/fasas
```

Docker Engine e Docker Compose di Ubuntu sono gratuiti e ricevono gli aggiornamenti di sicurezza automatici.
(Non serve Docker Desktop, che per le organizzazioni più grandi è a pagamento.)

### Passo 9. Lanciare lo script di preparazione

```bash
cd /opt/fasas && sudo ./scripts/prepara_server.sh
```

Le domande e cosa rispondere:

| Domanda | Risposta |
|---|---|
| Indirizzo del FASAS | quello del passo 7, es. `casarosa-fasas.duckdns.org` |
| Rete della struttura | di solito quella proposta (es. `192.168.1.0/24`): Invio. Da questa rete si entra con la password (più il codice per amministratori, coordinatori e medici); da fuori serve sempre il codice |
| Email dell'amministrazione | un indirizzo della struttura (serve al servizio delle notifiche push) |
| Bucket B2 già creato? | `n` la prima volta: si aggiunge al passo 13 |
| Token di DuckDNS | quello del passo 7 (non compare mentre lo si incolla) |
| Firewall | Invio (sì) |
| Riavvio automatico alle 05:15 | Invio (sì); `n` solo se avete scelto di digitare la frase del disco a ogni accensione (passo 5) |

Lo script crea il file `/opt/fasas/.env` con chiavi nuove (leggibile solo dall'amministratore), aggiorna
DuckDNS, attiva firewall e aggiornamenti automatici, costruisce e avvia il FASAS (la prima volta 5–15 minuti) e
controlla che il sito risponda in HTTPS con un certificato valido. Se si rilancia non rigenera mai le chiavi.

**Controllo da fuori**: su un telefono, **con il Wi-Fi spento**, aprire `https://casarosa-fasas.duckdns.org`:
deve comparire la pagina di accesso con il lucchetto. **Controllo da dentro**: dallo stesso indirizzo su un PC
della struttura. Se uno dei due non funziona, vedere «Problemi frequenti».

### Passo 10. Primo amministratore, verifica in due passaggi, utenti

```bash
cd /opt/fasas && sudo docker compose exec web python manage.py createsuperuser
```

1. **Dalla struttura** (la prima attivazione della verifica in due passaggi si fa solo dalla rete interna)
   entrare con l'utente appena creato: il FASAS chiede di attivare la **verifica in due passaggi**. Inquadrare il
   codice QR con l'app di autenticazione, scrivere il codice di 6 cifre.
2. **Stampare i codici di recupero** e metterli in cassaforte: servono se si perde il telefono.
3. In *Impostazioni* compilare i dati della struttura e la *Configurazione generale* (giorni di conservazione
   dei backup, promemoria delle terapie).
4. In *Utenti* creare un account per ogni persona, con il ruolo giusto, e consegnare la password iniziale di
   persona: ognuno la cambia subito da *Impostazioni › Cambia password*. Amministratori, coordinatori e medici
   attivano la verifica in due passaggi **in struttura**; chi vorrà entrare da casa deve attivarla anch'esso in
   struttura.
5. Il **medico** entra e valida i protocolli automatici (*Protocolli › Valida*) e, se usate, le interazioni
   farmacologiche: finché non li valida non sono attivi (docs/DISPOSITIVO_MEDICO.md).

### Passo 11. Busta di custodia delle chiavi

Le chiavi nel file `.env` aprono documenti e backup: se il server si guasta e le chiavi sono perse, **i backup
non servono più a nulla**. La busta è un file cifrato con una frase segreta che le contiene tutte.

```bash
cd /opt/fasas && sudo docker compose exec web python manage.py fasas_chiavi busta /data/busta-chiavi.fkey
```

1. Scegliere una **frase segreta** di almeno 12 caratteri (meglio 5 parole a caso), diversa da tutte le altre;
   salvarla nel gestore di password della direzione e sul foglio in cassaforte.
2. Il comando stampa il **foglio di custodia** con le impronte delle chiavi (non le chiavi): copiarlo, stamparlo,
   firmarlo e conservarlo con la chiavetta.
3. Formattare la chiavetta A in exFAT da un PC (come il disco al passo 14; se Windows non la formatta per intero
   dopo l'installazione di Ubuntu, usare un'altra chiavetta), collegarla al server e copiarci la busta:

```bash
cd /opt/fasas && sudo ./scripts/copia_backup_usb.sh --elenca
```

```bash
cd /opt/fasas && sudo ./scripts/copia_backup_usb.sh /dev/sdb1 --busta
```

   (al posto di `/dev/sdb1` il nome mostrato da `--elenca`). La chiavetta va **in cassaforte**, la frase
   **separata** dalla chiavetta (es. nel gestore di password della direzione). Una volta l'anno si prova ad aprirla
   (passo 18).

### Passo 12. Collaudo con il personale (prima dei dati veri)

Con un **ospite di prova** dal nome inventato (es. «Prova Collaudo») e documenti di prova, mai dati reali:

1. Registrare un parametro, una nota di diario, una somministrazione; caricare un PDF di prova.
2. Su 2–3 telefoni: aprire l'indirizzo, **Aggiungi alla schermata Home** (iPhone: *Condividi › Aggiungi alla
   schermata Home*, iOS 16.4 o successivo, poi aprire FASAS dall'icona), attivare le notifiche da *Impostazioni ›
   Notifiche sul telefono* e premere «Invia una notifica di prova» (docs/NOTIFICHE_E_SENZA_RETE.md).
3. Da un telefono con i dati mobili (fuori dalla rete della struttura) entrare con un utente qualsiasi: **deve**
   chiedere il codice della verifica in due passaggi.
4. In *Backup* premere «Esegui backup ora»: deve risultare riuscito e verificato.
5. Finito il collaudo, dimettere l'ospite di prova (la cartella resta archiviata).

Solo dopo il collaudo si inseriscono i dati veri.

---

## Parte E – Backup

Ogni notte il FASAS fa da solo un backup cifrato e lo verifica (docs/BACKUP.md). Una copia resta sul server: se
il server si rompe o viene rubato, servono le copie fuori sede (passo 13) e su disco USB (passo 14).

### Passo 13. Copia fuori sede gratuita su Backblaze B2

Backblaze riceve solo file **già cifrati** (la chiave resta alla struttura): non può leggere i dati.

1. Registrarsi su <https://www.backblaze.com> («B2 Cloud Storage», piano gratuito) con l'email della struttura.
   **Alla registrazione scegliere la regione «EU Central»** (data center in Europa: non si cambia dopo).
   **Non inserire la carta di credito.** Attivare la verifica in due passaggi dell'account.
2. In *Caps & Alerts* controllare che i limiti di spesa siano a 0 $: oltre la quota gratuita il servizio si
   ferma invece di addebitare.
3. *Buckets › Create a Bucket*: nome unico (es. `fasas-casarosa-7k2q`), **Files: Private**, **Default
   Encryption: Enable**, **Object Lock: Enable**. Annotare l'**Endpoint** mostrato nella pagina del bucket (es.
   `s3.eu-central-003.backblazeb2.com`).
4. *Application Keys › Add a New Application Key*: nome `fasas-server`, accesso **solo a quel bucket**, tipo
   **Read and Write**. Copiare subito **keyID** e **applicationKey** (la seconda si vede una volta sola).
5. Sul server aprire il file `.env`:

```bash
sudo nano /opt/fasas/.env
```

   e compilare le righe (si esce con `Ctrl+O`, `Invio`, `Ctrl+X`):

```
FASAS_OFFSITE_ENDPOINT=https://s3.eu-central-003.backblazeb2.com
FASAS_OFFSITE_REGION=eu-central-003
FASAS_OFFSITE_BUCKET=fasas-casarosa-7k2q
FASAS_OFFSITE_ACCESS_KEY=<keyID>
FASAS_OFFSITE_SECRET_KEY=<applicationKey>
```

   poi applicare:

```bash
cd /opt/fasas && sudo docker compose up -d
```

6. In *Backup* premere «Esegui backup ora»: la colonna «Fuori sede» deve indicare la copia e la data di fine
   blocco. Se compare un errore (es. permessi), ricreare la chiave come al punto 4; il backup locale non viene
   toccato e l'amministratore riceve comunque un avviso.
7. Rifare la busta delle chiavi (passo 11) con un nome nuovo, es. `/data/busta-chiavi-2.fkey`, così contiene
   anche la chiave B2.

**Spazio gratuito: 10 GB.** Lo script imposta una conservazione adatta: ogni copia resta **non cancellabile per
14 giorni** (nemmeno da chi ha le credenziali o da un ransomware), si tengono le ultime 7 giornaliere e 3 mensili.
Contemporaneamente ci sono al massimo circa 18 copie, quindi va bene finché **un backup pesa meno di 500 MB**
(la dimensione è nella pagina *Backup*). Se cresce, nel `.env` ridurre a `FASAS_OFFSITE_LOCK_DAYS=7` e
`FASAS_OFFSITE_KEEP_MONTHLY=1` (circa 9 copie, fino a 1 GB ciascuna); oltre, B2 diventa a pagamento: decidere
prima con la direzione.

### Passo 14. Copia mensile su disco USB

Il blocco di B2 dura 14 giorni: la copia mensile su un disco **scollegato** protegge anche da problemi scoperti
tardi.

1. Una volta sola, da un PC normale: formattare il disco B in **exFAT** (Windows: Esplora file › tasto destro
   sul disco › Formatta › File system exFAT; Mac: Utility Disco › Inizializza › ExFAT), nome `FASAS-BACKUP`.
2. **Il primo giorno lavorativo di ogni mese**: collegare il disco al server e, dal terminale:

```bash
cd /opt/fasas && sudo ./scripts/copia_backup_usb.sh --elenca
```

```bash
cd /opt/fasas && sudo ./scripts/copia_backup_usb.sh /dev/sdb1
```

   Lo script verifica l'ultimo backup (lo decifra e ne controlla l'impronta), lo copia, confronta la copia con
   l'originale, tiene sul disco gli ultimi 12 e smonta il disco.
3. Scollegare il disco e portarlo **in un altro luogo** (sede amministrativa, cassaforte della direzione): mai
   nella stessa stanza del server. Annotare data e firma su un registro.

---

## Parte F – Sicurezza, controllo e manutenzione

### Passo 15. Firewall e aggiornamenti automatici

Lo script del passo 9 ha già configurato:

- **firewall** (se si è risposto sì): da internet arrivano solo le porte 80 e 443 (al FASAS); SSH solo dalla rete
  della struttura. Controllo: `sudo ufw status`.
- **aggiornamenti di sicurezza** di Ubuntu e di Docker installati ogni giorno da soli; se serve un riavvio e si è
  risposto sì, avviene alle **05:15**, dopo i job notturni (2:00–4:15). Il FASAS riparte da solo.
- **accessi degli amministratori al server** (SSH, sudo) conservati in `/var/log/auth.log` per circa 7 mesi.

Per cambiare una risposta basta rilanciare `cd /opt/fasas && sudo ./scripts/prepara_server.sh`: le chiavi non
vengono toccate.

### Passo 16. Controllo gratuito dall'esterno

Il FASAS avvisa da solo l'amministratore di backup falliti, errori e problemi dell'audit. Se però il server è
spento o la linea è giù, non può avvisare nessuno: serve un controllo dall'esterno.

1. Registrarsi a un servizio gratuito di controllo dei siti, es. **UptimeRobot** (<https://uptimerobot.com>).
   **Prima leggere le condizioni del piano gratuito**: quando le abbiamo controllate le pagine di UptimeRobot non
   erano concordi sull'uso da parte di organizzazioni; se non è consentito, scegliere un altro servizio gratuito
   che lo consenta.
2. Nuovo controllo di tipo **HTTP(s)** sull'indirizzo `https://casarosa-fasas.duckdns.org/salute/`, ogni 5
   minuti, avviso via email all'amministrazione (e, se c'è l'app, sul telefono).
3. Il servizio riceve solo l'indirizzo e la risposta `ok`/errore: nessun dato degli ospiti.

### Passo 17. Prima prova di ripristino

In *Backup › Prova di ripristino*: il FASAS riapre l'ultimo backup (dalla copia fuori sede, se c'è) in un database
separato, controlla audit e dati e prepara il **verbale** da stampare, firmare e archiviare. Poi si ripete da sola
il primo giorno di gennaio, aprile, luglio e ottobre.

### Passo 18. Calendario della manutenzione

| Quando | Cosa | Tempo |
|---|---|---|
| Ogni giorno | niente: backup, verifiche e aggiornamenti sono automatici. Leggere le notifiche del FASAS | — |
| Ogni settimana | *Impostazioni › Stato del sistema ed errori*: controlli tutti verdi | 2 min |
| Ogni mese | copia su disco USB (passo 14); in Backblaze lo spazio usato resta sotto 9 GB | 10 min |
| Ogni 3 mesi | stampare e firmare il verbale della prova di ripristino automatica | 5 min |
| Ogni anno | provare la busta delle chiavi (sotto); togliere gli utenti di chi non lavora più; controllare la batteria del gruppo di continuità; spolverare il server; controllare che il router abbia l'ultimo aggiornamento | 1 ora |

**Prova annuale della busta**: collegare la chiavetta A al server (con `--elenca` del passo 14 si vede il nome,
es. `/dev/sdb1`). Il secondo comando chiede la frase segreta e **mostra le chiavi a schermo**: farlo da soli, poi
chiudere il terminale.

```bash
sudo mount /dev/sdb1 /mnt
```

```bash
cd /opt/fasas && sudo docker compose run --rm --no-deps -v /mnt/FASAS-busta-chiavi:/busta:ro web python manage.py fasas_chiavi apri /busta/busta-chiavi.fkey
```

```bash
sudo umount /mnt
```

Se avete rifatto la busta (passo 13.7) usare il nome più recente, es. `busta-chiavi-2.fkey`. Le righe stampate
devono essere uguali a quelle del file `.env` (`sudo grep -E "KEY|TOKEN" /opt/fasas/.env`).
Il comando lavora in un contenitore temporaneo che legge la chiavetta in sola lettura e poi sparisce.

**Aggiornare il FASAS a una nuova versione** (non automatico, apposta):

1. leggere `CHANGELOG.md` della nuova versione; se possibile provarla prima su un altro PC con dati di fantasia
   (docs/CONTAINER.md, «Ambiente di prova separato»);
2. in *Backup* «Esegui backup ora», poi:

```bash
cd /opt/fasas && sudo git pull && sudo docker compose up -d --build
```

3. entrare e controllare le funzioni principali. Tornare indietro non si fa con `git`: le modifiche al database
   vanno solo avanti, si ripristina il backup del punto 2.

---

## Problemi frequenti

**Da fuori il sito non si apre.**
1. L'indirizzo punta all'IP giusto? Nella pagina di duckdns.org la colonna «current ip» deve essere uguale
   all'indirizzo mostrato da <https://ifconfig.me> aperto in struttura. Se no, sul server:
   `sudo /usr/local/sbin/fasas-duckdns` e i messaggi con `journalctl -t fasas-duckdns`.
2. Inoltro delle porte 80 e 443 verso l'indirizzo giusto del server (passo 6), protocollo TCP.
3. CGNAT (passo 1a).

**Da fuori funziona, dalla struttura no (o il contrario).** Molti router non sanno «tornare indietro» verso un
PC interno usando l'indirizzo pubblico (NAT loopback). Soluzioni, dalla migliore:
1. nel router, sezione DNS («DNS locale», «Host name mapping»), associare `casarosa-fasas.duckdns.org`
   all'indirizzo interno del server (es. `192.168.1.50`);
2. se il router non lo permette, sui PC fissi della struttura aggiungere al file `hosts` la riga
   `192.168.1.50 casarosa-fasas.duckdns.org` (Windows: `C:\Windows\System32\drivers\etc\hosts`, aprendo il Blocco
   note come amministratore). I telefoni in struttura in quel caso usano i dati mobili, con il codice.

**Il browser avvisa che il certificato non è valido.** Il certificato si ottiene solo se le porte 80/443 arrivano
al server da internet. Guardare `cd /opt/fasas && sudo docker compose logs --tail 50 proxy`; sistemato l'inoltro,
Caddy riprova da solo (attendere fino a un'ora se ci sono stati molti tentativi).

**Dopo un blackout o un aggiornamento il server non riparte / chiede la frase del disco.** Dopo un aggiornamento
del BIOS o delle regole di Secure Boot il TPM può non riconoscere più l'avvio: chi ha la frase di cifratura la
digita alla tastiera del server. Poi, per ripristinare lo sblocco automatico:

```bash
DISCO=$(sudo blkid -t TYPE=crypto_LUKS -o device | head -n 1); sudo clevis luks list -d "$DISCO"
```

```bash
sudo clevis luks regen -d "$DISCO" -s 1
```

(al posto di `1` il numero mostrato prima dei due punti dal comando precedente). Se il server non si riaccende
proprio, controllare l'impostazione «Power On» del passo 2.

**Un operatore ha perso o cambiato telefono.** L'amministratore in *Utenti* preme «Reimposta» nella colonna
della verifica in due passaggi; l'operatore la riattiva al primo accesso **dalla struttura**. In alternativa può
entrare con uno dei suoi codici di recupero.

**Un operatore è bloccato dopo troppi tentativi.** Si sblocca da solo dopo 15 minuti.

**Disco del server quasi pieno** (avviso del FASAS sotto 5 GB liberi). Ridurre i giorni di conservazione dei
backup in *Configurazione* e togliere le vecchie immagini di Docker (non tocca i dati):

```bash
sudo docker image prune -af
```

**Copia fuori sede in errore.** Il messaggio è nella pagina *Backup*. Di solito: chiave B2 sbagliata o senza
permessi (passo 13.4), spazio gratuito finito (ridurre la conservazione), Backblaze irraggiungibile (riprova la
notte dopo).

**Il server è guasto o è stato rubato.** Su un PC nuovo: passi 2–8 e lo script del passo 9 (crea chiavi nuove e
un database vuoto). Poi:

1. recuperare le chiavi originali dalla busta (chiavetta in cassaforte e frase segreta) con i comandi della
   «Prova annuale della busta» (passo 18);
2. nel `.env` sostituire con quelle della busta le righe `DJANGO_SECRET_KEY`, `FASAS_ENCRYPTION_KEYS`,
   `FASAS_BACKUP_KEY`, `FASAS_VAPID_PRIVATE_KEY`, `FASAS_HEALTH_TOKEN` (e la chiave B2) e applicare con
   `sudo docker compose up -d`;
3. copiare sul server l'ultimo backup (dal disco USB, o scaricato da Backblaze) e ripristinarlo seguendo
   «Ripristino vero» in docs/BACKUP.md (applicazione ferma, `backup_restore … --confirm`, poi `audit_verify`);
4. cambiare la password di chi ha accesso al server, al router, a DuckDNS e a Backblaze; se il server è stato
   rubato, valutare con il DPO la notifica di violazione al Garante (72 ore).

---

## Cosa è stato verificato e cosa no

- Gli script `scripts/prepara_server.sh` e `scripts/copia_backup_usb.sh` sono stati provati con router, DuckDNS e
  disco USB simulati; `prepara_server.sh` gira anche a ogni modifica su un vero Ubuntu 24.04 con Docker nella CI
  di GitHub (job «installazione»: crea il `.env`, avvia tutto, controlla HTTPS, chiavi e che un secondo avvio non
  cambi le chiavi).
- **Non** sono stati provati su hardware reale: l'installazione di Ubuntu, lo sblocco con il TPM e la password di
  GRUB (passo 5), un router vero e il certificato di Let's Encrypt per un indirizzo DuckDNS, il caricamento su un
  vero bucket Backblaze con Object Lock (il FASAS lo prova con un simulatore S3). Per questo i passi 9, 12 e 13
  contengono un controllo esplicito: se non dà il risultato atteso, fermarsi e risolvere prima dei dati veri.

## Cosa resta fuori da questa guida

- **Privacy**: DPIA, registro dei trattamenti, informative e nomine (bozze in `docs/gdpr/`): Backblaze e il
  servizio di controllo vanno indicati nel registro; per Backblaze serve il suo accordo sul trattamento dei dati
  (DPA) pubblicato da Backblaze: verificare come sottoscriverlo. Chi gestisce il server va nominato **amministratore di sistema**.
- **Sicurezza fisica**: il server in un locale chiuso, l'elenco di chi ne ha la chiave.
- **Assistenza**: una seconda persona che conosca questa guida, per ferie e malattie.
- **Firma con CIE, dispositivo medico, assicurazione**: docs/FIRMA_CIE.md e docs/DISPOSITIVO_MEDICO.md.
