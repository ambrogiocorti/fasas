# Notifiche sul telefono e lavoro senza rete

FASAS Digitale si installa sul telefono o sul tablet come un'app (PWA): **Aggiungi alla schermata Home** dal browser.
Così riceve le notifiche push e continua a funzionare quando la rete cade.

## Notifiche push

### Cosa arriva sul telefono

Gli avvisi che l'amministratore ha impostato come «Push» in *Impostazioni → Notifiche* (di default: protocolli
attivati, eventi critici ed emergenze, SOS da validare, visite di oggi, esito dei backup, integrità dell'audit log).
Ognuno arriva solo a chi ha il ruolo e il permesso per aprirlo.

**Riservatezza**: la notifica sulla schermata di blocco mostra solo il tipo di avviso, per esempio
«FASAS · Protocollo attivato», mai il nome dell'ospite o dati clinici. Toccandola si apre FASAS (con l'accesso)
sulla pagina giusta. Il contenuto viaggia cifrato end-to-end (RFC 8291): il servizio push del produttore
(Google, Apple, Mozilla) non lo può leggere. Chi usa solo dispositivi personali protetti può mostrare il testo
completo con `FASAS_PUSH_SHOW_DETAILS=1`.

### Attivazione

1. **Amministratore, una volta sola**: `python manage.py fasas_vapid_keys` e copiare la riga
   `FASAS_VAPID_PRIVATE_KEY=...` nel file `.env`; impostare anche `FASAS_VAPID_SUBJECT=mailto:...` con un indirizzo
   della struttura; riavviare. La chiave non va cambiata: se cambia, ogni dispositivo va riattivato.
2. **Ogni operatore, su ogni dispositivo**: *Impostazioni → Notifiche sul telefono → Attiva le notifiche su questo
   dispositivo* e consentire le notifiche quando il browser lo chiede. Con **Invia una notifica di prova** si verifica.
   - **Android** (Chrome, Edge, Firefox) e **computer**: funziona dal browser.
   - **iPhone/iPad** (iOS 16.4 o successivo): prima *Condividi → Aggiungi alla schermata Home*, poi aprire FASAS
     dall'icona e attivare da lì.
3. Il sito deve essere in **HTTPS** (in prova va bene anche `localhost`).

Sui tablet condivisi del reparto le notifiche arrivano all'ultimo utente che le ha attivate su quel tablet.

## Lavorare senza rete

### Prima: niente da fare

Ogni dispositivo usato da un operatore (permesso «lavorare in modalità offline», incluso in Operatore e
Coordinatore) scarica in automatico, ogni 30 minuti, il **pacchetto del turno** in corso e del successivo:
dosi da somministrare con lo stato, farmaci al bisogno con limiti e ultime somministrazioni, allergie, avvisi dei tag,
dieta, protocolli aperti, ultimi parametri, contatti di emergenza. Il menu **Turno → Senza rete** mostra se il
dispositivo è pronto. Ogni scaricamento è registrato nell'audit log.

### Durante: si continua a lavorare

Quando la rete o il server non rispondono, qualunque pagina di FASAS apre la **modalità senza rete**:

- si sblocca con la **propria password** di FASAS (funziona senza rete);
- **Giro farmaci**: somministrato / rifiutato / non dato per ogni dose del turno;
- **Ospiti**: allergie e avvisi, protocolli da seguire, farmaci SOS (con motivo e controllo dei limiti),
  parametri, diario, eventi;
- **Stampa** stampa il giro farmaci del momento;
- **Blocca** chiude i dati; si bloccano da soli dopo l'inattività configurata (come la sessione online).

### Dopo: si sincronizza da solo

Al ritorno della rete (e dopo l'accesso, se la sessione è scaduta) le registrazioni partono da sole, con **l'ora reale
in cui sono state fatte**. Ogni registrazione ha un identificativo unico: un invio ripetuto non crea doppioni.

| Esito | Significato |
|---|---|
| Registrata | entrata normalmente nella cartella |
| Registrata in un turno già chiuso | il turno era stato chiuso (anche automaticamente) durante l'interruzione: la registrazione è accettata come tardiva |
| Già registrata da un altro operatore | la stessa dose era stata registrata da un altro dispositivo: non viene duplicata |
| Non registrata | dati non validi (es. ora nel futuro, oltre 72 ore, permesso mancante) |

Gli esiti diversi da «Registrata» compaiono in **Turno → Senza rete** e arrivano al coordinatore come notifica.
Nell'audit log queste registrazioni hanno origine **offline** e la motivazione con data e ora reali e di invio.

### Sicurezza dei dati sul dispositivo

- Pacchetto e registrazioni in attesa sono **cifrati (AES-256-GCM)** con una chiave che si apre solo con la password
  dell'utente (PBKDF2, 300.000 iterazioni): chi prende il tablet senza la password non legge i dati.
- Il service worker conserva solo l'«involucro» dell'applicazione (pagina, stile, script, icone), mai pagine o dati
  sanitari.
- I dati del pacchetto si cancellano dopo 72 ore; le registrazioni inviate dopo 24 ore.
- Se la password viene cambiata dall'utente (*Cambia password*) i dati restano leggibili. Se viene reimpostata
  dall'amministratore, le registrazioni non ancora inviate da quel dispositivo non sono più leggibili: prima di
  reimpostare una password, far sincronizzare il dispositivo.
- Usare tablet con blocco schermo e un profilo del browser dedicato al reparto.

### Se mancano anche i dispositivi: foglio di emergenza

**Turno → Senza rete → Foglio di emergenza (PDF)**: per ogni ospite allergie, avvisi, terapie della giornata con la
colonna «ora e sigla», farmaci al bisogno con limiti, contatti di emergenza. Stamparlo a inizio giornata e tenerlo in
infermeria; al ripristino si riporta in FASAS quanto annotato.
