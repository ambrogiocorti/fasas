# FASAS su https://fasas.online

Guida per portare il FASAS sul dominio `fasas.online` con **un solo codice**: lo stesso repository della versione
locale, con configurazioni diverse. Nessuna seconda copia da mantenere a mano.

## Stato rilevato l'8/11/2026

| Cosa | Stato |
|---|---|
| DNS (Register.it, `ns1/ns2.register.it`) | `fasas.online` → `185.199.108-111.153` (GitHub Pages); `www.fasas.online` → `ambrogiocorti.github.io` |
| Cosa risponde | la pagina GitHub Pages del README di `fasas-deploy`: **pagine statiche, nessun Django** (`/accesso/entra/` e `/salute/` danno 404) |
| Server Django | non pubblicato da nessuna parte |
| Supabase | l'unico progetto dell'account è **«breakapp-dev»**, di un'altra applicazione: **non va usato per il FASAS** (il FASAS ora si rifiuta di partire in un database con tabelle di altre applicazioni) |
| `fasas-deploy` | copia ridotta di questo repository con due aggiunte utili, ora integrate qui (dominio unico, avvio per hosting Python). Si può archiviare quando il dominio non serve più a GitHub Pages |

## Quale hosting (verifica di novembre 2026, prezzi da ricontrollare al momento dell'acquisto)

Un sistema con dati sanitari ha bisogno di un server **sempre acceso**, in UE, con un contratto sul trattamento dei
dati (art. 28). Nessuna offerta gratuita verificata soddisfa questi requisiti:

| Opzione | Costo | Perché sì / perché no |
|---|---|---|
| **VPS in UE + stack Docker del FASAS** (consigliata) | circa 6–8 € al mese + IVA: Aruba Cloud VPS da 6,29 €/mese (data center in Italia), Hetzner CX23 circa 5,49 €/mese (Germania/Finlandia, a volte esaurito), OVHcloud | sempre acceso; database, job, HTTPS automatico e backup già collaudati a ogni modifica nella CI (job «installazione-vps»); un solo fornitore a cui chiedere l'accordo art. 28 |
| Render gratuito + Supabase gratuito | 0 € | il servizio si addormenta, Supabase gratuito non fa backup giornalieri e va in pausa dopo 7 giorni di scarsa attività; con Render hai già avuto problemi di registrazione e pagamento. Va bene solo per prove con dati inventati ([CLOUD.md](CLOUD.md)) |
| Render a pagamento + Supabase Pro | piani mensili a pagamento (prezzi sui siti) | gestito e sempre acceso, ma costa più volte un VPS e richiede due fornitori |
| Koyeb | più fonti riportano che dal 2026 i nuovi account non hanno più un piano gratuito | — |
| Oracle Cloud Always Free | 0 € con carta di verifica | le istanze poco usate vengono recuperate (un FASAS di una comunità lo è), capacità non garantita |
| Enzonic | — | già risultato inutilizzabile (registrazione, disponibilità, pagamento) |
| GitHub Pages | 0 € | serve solo pagine statiche: **non può eseguire Django** |

La scelta del fornitore e la spesa sono decisioni della struttura. Questa guida usa un VPS.

## Passo 1 – VPS

1. Ordinare un VPS **Ubuntu 24.04**, almeno 2 GB di RAM (meglio 4 GB), 40 GB di disco, regione UE, con **chiave
   SSH** (non password). Annotare l'indirizzo IPv4 (e IPv6 se c'è).
2. Nel pannello del fornitore: porte 22, 80 e 443 aperte (se c'è un firewall del fornitore); backup/snapshot del
   fornitore facoltativi (il FASAS fa i suoi, cifrati).
3. Firmare l'accordo sul trattamento dei dati del fornitore (di solito nel pannello, sezione privacy/GDPR).

## Passo 2 – DNS su Register.it

Pannello Register.it › Domini › `fasas.online` › **Gestione DNS** (o «DNS e puntamenti»):

| Tipo | Nome | Valore | Azione |
|---|---|---|---|
| A | `@` (fasas.online) | `185.199.108.153`, `.109.153`, `.110.153`, `.111.153` | **togliere** (sono di GitHub Pages) |
| A | `@` | IPv4 del VPS | **aggiungere** |
| AAAA | `@` | IPv6 del VPS | aggiungere solo se il VPS ha IPv6 |
| CNAME | `www` | `ambrogiocorti.github.io` | **cambiare** in `fasas.online.` |
| CAA | `@` | `0 issue "letsencrypt.org"` | facoltativo: solo Let's Encrypt può emettere certificati |

Poi su GitHub › `fasas-deploy` › Settings › **Pages**: togliere il dominio personalizzato `fasas.online` (e il file
`CNAME`), altrimenti GitHub continua a considerarlo suo.

Controllo (dopo qualche minuto, a volte fino a qualche ora):

```bash
nslookup fasas.online
```

deve rispondere con l'IP del VPS; `nslookup www.fasas.online` con `fasas.online` e lo stesso IP.

## Passo 3 – Server

Dal proprio PC:

```bash
ssh root@IP_DEL_VPS
```

Sul server (una volta):

```bash
adduser --disabled-password --gecos "" fasas && usermod -aG sudo fasas && install -d -m 700 -o fasas -g fasas /home/fasas/.ssh && cp ~/.ssh/authorized_keys /home/fasas/.ssh/ && chown fasas:fasas /home/fasas/.ssh/authorized_keys && passwd fasas
```

```bash
printf 'PasswordAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/10-fasas.conf && systemctl reload ssh
```

Da un'altra finestra controllare di poter entrare come `fasas` **prima** di chiudere quella di root. Poi, come `fasas`:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git curl
```

```bash
sudo git clone -b claude/fasas-digital-system-5v69px https://github.com/ambrogiocorti/fasas.git /opt/fasas
```

```bash
cd /opt/fasas && sudo ./scripts/prepara_server.sh --vps
```

Lo script chiede il dominio (`fasas.online`), gli altri nomi (`www.fasas.online`), l'email per le notifiche e la
copia fuori sede; crea il `.env` con chiavi nuove, controlla che il DNS punti al server, attiva firewall (80, 443 e
SSH con limite ai tentativi) e aggiornamenti di sicurezza, avvia database, sito, job e HTTPS con certificato
Let's Encrypt. Si può rilanciare: le chiavi non cambiano.

## Passo 4 – Primo accesso e chiavi

```bash
cd /opt/fasas && sudo docker compose exec web python manage.py createsuperuser
```

Entrare da `https://fasas.online` e attivare la verifica in due passaggi. Poi la busta di custodia delle chiavi
([INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md), passo 11): senza le chiavi documenti e backup non
si leggono più.

## Passo 5 – Backup fuori sede e monitoraggio

- Copia fuori sede cifrata con blocco delle modifiche su Backblaze B2 (gratuito fino a 10 GB):
  [INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md), passo 13. Senza, i backup restano solo sul VPS.
- Controllo dall'esterno (gratuito) su `https://fasas.online/salute/`: [MONITORAGGIO.md](MONITORAGGIO.md).
- La prova di ripristino trimestrale parte da sola sul database di prova del server (Sistema › Backup).

## Passo 6 – Pubblicare le nuove versioni da GitHub

Sul server, utente dedicato alla pubblicazione con il solo permesso di lanciare l'aggiornamento:

```bash
sudo adduser --disabled-password --gecos "" pubblica && echo 'pubblica ALL=(root) NOPASSWD: /opt/fasas/scripts/aggiorna_fasas.sh' | sudo tee /etc/sudoers.d/fasas-pubblica && sudo chmod 440 /etc/sudoers.d/fasas-pubblica
```

Sul proprio PC, una chiave solo per GitHub:

```bash
ssh-keygen -t ed25519 -N "" -C "github-pubblica-fasas" -f pubblica-fasas
```

La parte pubblica (`pubblica-fasas.pub`) va in `/home/pubblica/.ssh/authorized_keys` sul server. Su GitHub ›
repository `fasas` › Settings › **Environments** › New environment `fasas-online`:

- **Required reviewers**: sé stessi (ogni pubblicazione va approvata);
- segreti: `SERVER_HOST` (IP del VPS), `SERVER_USER` (`pubblica`), `SERVER_SSH_KEY` (contenuto di `pubblica-fasas`),
  `SERVER_KNOWN_HOSTS` (riga ottenuta con `ssh-keyscan -t ed25519 IP_DEL_VPS`, confrontando l'impronta con quella
  mostrata nella console del fornitore).

Da quel momento: Actions › **Pubblica su fasas.online** › Run workflow. Il workflow accetta solo commit con la CI
verde, fa backup, porta il server alla versione scelta, controlla che risponda e altrimenti **torna da solo alla
versione di prima**; alla fine verifica `https://fasas.online/salute/` dall'esterno.

## Tornare indietro a mano

```bash
cd /opt/fasas && sudo ./scripts/aggiorna_fasas.sh --versione COMMIT_DI_PRIMA
```

Se una versione aveva cambiato il database e serve anche il database di prima: ripristinare il backup fatto
all'inizio dell'aggiornamento ([BACKUP.md](BACKUP.md), «Ripristino»), dopo averlo provato su una copia.

## Controllo finale

- [ ] `https://fasas.online` con lucchetto valido; `http://` e `www.` rimandano a `https://fasas.online`
- [ ] `https://fasas.online/salute/` risponde `"status": "ok"` (o `degraded` solo per il backup non ancora fatto)
- [ ] accesso, verifica in due passaggi, uscita; pagina di amministrazione solo con utente autorizzato
- [ ] la mattina dopo: backup delle 02:30 verificato e copiato fuori sede (Sistema › Backup)
- [ ] busta di custodia chiusa e firmata

## Prima dei dati veri

Il server funzionante non basta: servono accordi art. 28 con il fornitore del VPS (e di B2), registro dei
trattamenti e DPIA aggiornati, valutazione del DPO sul fatto che il database non è cifrato dal FASAS (lo sono i
documenti e i backup), collaudo del pilota e gli adempimenti di [ADEMPIMENTI_PRIMA_DELL_AVVIO.md](ADEMPIMENTI_PRIMA_DELL_AVVIO.md).
