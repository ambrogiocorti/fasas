# Piano di continuità: il fascicolo non manca mai

Il FASAS, come qualunque sistema informatico (anche negli ospedali), può fermarsi: un guasto, un blackout, la
linea internet, un attacco. Questo piano fa in modo che **la comunità non resti mai senza fascicolo**: il lavoro
continua durante l'interruzione, i dati non si perdono e dopo si torna alla normalità con una procedura scritta.
È una bozza da completare con i nomi e i numeri della struttura e da approvare dalla direzione; va mostrata
all'ATS insieme alla presentazione del fascicolo digitale.

## Obiettivi

| Obiettivo | Come si raggiunge |
|---|---|
| Durante un'interruzione il turno lavora senza fermarsi | modalità senza rete sui tablet (turno in corso e successivo) e foglio di emergenza stampato |
| Si perdono al massimo pochi minuti di registrazioni | disco di continuità con copia ogni 5 minuti; copia notturna fuori sede non cancellabile per 14 giorni; copia mensile scollegata |
| In struttura il FASAS funziona anche senza linea internet | DNS locale del router (guida d'installazione, passo 7b) |
| Ripartenza dopo un guasto del server | ripristino dal disco di continuità su un PC sostitutivo, con la guida: obiettivo [__ ore] |
| Ogni interruzione è documentata | registro delle interruzioni in fondo a questo piano |

## Chi fa cosa

| Ruolo | Persona | Telefono |
|---|---|---|
| Responsabile del piano (direzione) | [nome] | [numero] |
| Amministratore di sistema | [nome] | [numero] |
| Sostituto dell'amministratore | [nome] | [numero] |
| DPO (per sospette violazioni di dati) | [nome] | [numero] |
| Coordinatore di turno | chi è in turno | — |

## Ogni giorno, prima che serva

- Tablet di reparto carichi; in **Turno › Senza rete** il dispositivo risulta «pronto» (il pacchetto del turno si
  scarica da solo ogni 30 minuti).
- **Foglio di emergenza** stampato a inizio giornata (terapie del giorno, allergie, avvisi, contatti) e tenuto in
  [luogo: es. cassetto dell'infermeria]. Si stampa dal FASAS: Turno › Senza rete › Foglio di emergenza.
- Server, router e Wi-Fi collegati al gruppo di continuità; disco di continuità collegato (riga verde in
  *Stato del sistema*).

## Cosa fare quando succede

| Evento | Cosa fa il turno | Cosa fa l'amministratore di sistema |
|---|---|---|
| **Manca la corrente** | continua sui tablet (a batteria) in modalità senza rete; se si scaricano, foglio di emergenza | se il blackout dura più dell'autonomia del gruppo di continuità, spegnere il server prima che la batteria finisca (lo spegnimento automatico dalla porta USB del gruppo non è ancora configurato); al ritorno della corrente il server si riaccende da solo: controllare *Stato del sistema* |
| **Cade la linea internet** | in struttura nulla cambia (con il DNS locale); da casa non si entra | segnalare il guasto all'operatore telefonico |
| **Il FASAS non risponde** (guasto del server) | modalità senza rete sui tablet, poi foglio di emergenza; annotare a mano ciò che non si registra | avvisato dal servizio di controllo esterno; se il server non riparte: PC sostitutivo, ripristino dal disco di continuità (guida, passo 14b) |
| **Avviso «copia continua NON riuscita»** | nulla | ricollegare il disco di continuità: `disco_continuita.sh --rimonta` |
| **Sospetto attacco** (file illeggibili, schermate strane, richieste di riscatto) | foglio di emergenza; non usare il server | staccare il cavo di rete del server (non spegnerlo); avvisare DPO e direzione: procedura violazioni (72 ore); ripristino su un server pulito dalle copie non cancellabili |
| **Furto o incendio del server** | come il guasto | denuncia; procedura violazioni; nuovo PC; ripristino dalla copia fuori sede e da quella mensile |
| **Tablet perso o rubato** | usare un altro dispositivo | i dati sul tablet sono cifrati: disattivare l'utente o cambiarne la password; annotare nel registro violazioni |

## Ritorno alla normalità

1. Le registrazioni fatte sui tablet senza rete partono da sole, con l'ora reale in cui sono state fatte.
2. Quanto scritto sul foglio di emergenza si inserisce nel FASAS con l'ora reale. Se nel frattempo il turno è stato
   chiuso (anche in automatico, al riavvio del server), l'amministratore lo riapre in via straordinaria con la
   motivazione «registrazioni dal foglio di emergenza», si inseriscono i dati e lo si richiude. La riapertura va
   abilitata in anticipo in *Configurazione generale*: è una decisione della direzione da prendere ora.
3. Il coordinatore controlla in **Turno › Senza rete** gli esiti diversi da «Registrata».
4. Si compila il registro delle interruzioni.

## Prove

| Quando | Prova | Chi |
|---|---|---|
| Ogni 6 mesi | un turno di prova in modalità senza rete e con il foglio di emergenza | coordinatore |
| Ogni 6 mesi | staccare la spina del gruppo di continuità e misurare quanto restano accesi server, router e Wi-Fi | amministratore di sistema |
| Ogni 3 mesi | verbale della prova di ripristino automatica (pagina *Backup*), firmato | amministratore di sistema |
| Ogni anno | apertura di prova della busta delle chiavi; ripristino di prova dal disco di continuità su un altro PC | amministratore di sistema e sostituto |

## Registro delle interruzioni

| Data e ora | Durata | Causa | Come si è lavorato | Dati da reinserire | Firma |
|---|---|---|---|---|---|
| | | | | | |

---

*Il piano descrive le misure tecniche disponibili nel FASAS e nella guida d'installazione; tempi di ripartenza e
risorse (PC sostitutivo, reperibilità) li decide la direzione. Non è un parere legale né un requisito dell'ATS:
verificare con l'ATS che cosa richiede per il fascicolo digitale.*
