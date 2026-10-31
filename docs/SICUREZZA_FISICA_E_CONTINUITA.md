# Sicurezza fisica e continuità del FASAS in struttura

Il server è nella struttura: la porta del locale, la cassaforte e la persona che sa cosa fare sono misure di
sicurezza come le password. Questa pagina contiene le regole e i moduli da stampare. Riferimento tecnico:
[INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md).

## 1. Il locale del server

- Porta **chiusa a chiave**; non è un ripostiglio di passaggio né una sala comune.
- Niente tubi d'acqua o termosifoni sopra il server; non a contatto con il pavimento se il locale può allagarsi;
  temperatura sotto i 30 °C; prese di ventilazione libere.
- Server, router e modem sotto il **gruppo di continuità**; nessun altro apparecchio collegato al gruppo.
- Un estintore adatto alle apparecchiature elettriche (CO₂) nelle vicinanze, come da piano antincendio.
- Il server non ha monitor e tastiera collegati in modo permanente.

### Registro delle chiavi del locale

| N. chiave | Consegnata a | Ruolo | Data consegna | Firma | Data restituzione | Firma |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |

## 2. Cassaforte e supporti

| Oggetto | Dove sta | Chi può accedervi | Controllato il |
|---|---|---|---|
| Chiavetta della **busta delle chiavi** (guida, passo 11) | cassaforte [ ] | [ ] | |
| Foglio con **frase della busta** | **separato** dalla chiavetta: [gestore di password della direzione / seconda cassaforte] | [ ] | |
| Foglio con **frase di cifratura del disco**, password del BIOS e di GRUB | cassaforte [ ] | [ ] | |
| **Codici di recupero** della verifica in due passaggi degli amministratori | cassaforte [ ] | [ ] | |
| **Disco USB dei backup** (guida, passo 14) | luogo **diverso dal locale del server**: [ ] | [ ] | |
| Foglio di custodia firmato con le impronte delle chiavi | con la chiavetta | [ ] | |

Gestore di password: un archivio della struttura (non personale) a cui accedono amministratore di sistema e vice,
con le password di router, DuckDNS, Backblaze, servizio di controllo e utente del server.

### Registro del disco USB mensile

| Data | Copia eseguita da | Backup copiato (nome file) | Disco riportato in [luogo] da | Firma |
|---|---|---|---|---|
| | | | | |
| | | | | |

## 3. Due persone, non una

Il FASAS non deve dipendere da una sola persona. Servono un **amministratore di sistema** e un **vice**, entrambi
nominati ([gdpr/MODELLO_NOMINA_AMMINISTRATORE_SISTEMA.md](gdpr/MODELLO_NOMINA_AMMINISTRATORE_SISTEMA.md)), ciascuno
con **le proprie credenziali** (mai condivise):

- un proprio utente nel FASAS con ruolo amministratore e verifica in due passaggi;
- un proprio utente sul server. L'amministratore lo crea per il vice (dalla rete della struttura):

```bash
sudo adduser nome.cognome && sudo usermod -aG sudo nome.cognome
```

- accesso al gestore di password della struttura.

### Come si prepara il vice

1. Legge la guida d'installazione e questa pagina.
2. Esegue lui **una copia mensile su disco USB ogni tre mesi** (passo 14), con l'amministratore accanto la prima
   volta.
3. Una volta l'anno fa da solo la **prova annuale della busta** (guida, passo 18) e una **prova di ripristino**
   dalla pagina *Backup*.
4. Sa dove sono la cassaforte, il registro delle chiavi e la procedura per le violazioni.

### Scheda del sostituto (da compilare e tenere in cassaforte)

| Voce | |
|---|---|
| Indirizzo del FASAS | https://[ ].duckdns.org |
| Indirizzo del server nella rete della struttura | 192.168.[ ].[ ] |
| Dove sono il server, il router, il gruppo di continuità | [ ] |
| Dove sono le chiavi del locale e della cassaforte | [ ] |
| Cartella del FASAS sul server | `/opt/fasas` |
| Amministratore di sistema | [nome, telefono] |
| Vice | [nome, telefono] |
| DPO | [nome, telefono] |
| Assistenza tecnica esterna, se c'è | [ ] |
| Operatore internet (assistenza linea) | [numero, codice cliente] |

Problemi più comuni e cosa fare: guida d'installazione, sezione «Problemi frequenti». In caso di possibile
violazione di dati: [gdpr/PROCEDURA_VIOLAZIONI.md](gdpr/PROCEDURA_VIOLAZIONI.md).

## 4. Quando un amministratore lascia

Lo stesso giorno in cui finisce l'incarico:

1. Nel FASAS: disattivare il suo utente.
2. Sul server: togliere il suo utente.

```bash
sudo deluser --remove-home nome.cognome
```

3. Cambiare le password che conosceva: router, DuckDNS, Backblaze (e rigenerare la chiave d'accesso B2 nel `.env`),
   servizio di controllo, gestore di password della struttura, BIOS e GRUB.
4. Se conosceva la **frase di cifratura del disco**, cambiarla (chiede la frase attuale e poi quella nuova):

```bash
DISCO=$(sudo blkid -t TYPE=crypto_LUKS -o device | head -n 1); sudo cryptsetup luksChangeKey "$DISCO"
```

5. Se conosceva la **frase della busta**, creare una busta nuova con una frase nuova (guida, passo 11) e
   distruggere la vecchia chiavetta o sovrascriverla.
6. Restituzione delle chiavi del locale (registro sopra); aggiornare l'elenco degli amministratori di sistema e la
   scheda del sostituto.

## 5. Verifica annuale

Una volta l'anno la direzione (o il DPO) controlla, e lo mette per iscritto: registro delle chiavi, registro del
disco mensile, contenuto della cassaforte, utenti attivi del FASAS e del server, esecuzione del calendario di
manutenzione, verbali delle prove di ripristino, preparazione del vice.
