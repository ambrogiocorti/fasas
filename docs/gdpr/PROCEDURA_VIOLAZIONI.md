# Procedura per le violazioni di dati personali (data breach) – bozza

> **Bozza da completare e far approvare al DPO.** Riferimenti: artt. 33 e 34 GDPR; Linee guida EDPB 9/2022 sulla
> notifica delle violazioni. Stampare la prima pagina e tenerla vicino al server e in amministrazione.

## Che cos'è una violazione

Qualsiasi evento che rende i dati personali **persi, distrutti, modificati, divulgati o accessibili** a chi non
dovrebbe, anche per errore. Esempi con il FASAS:

- server, disco USB dei backup o chiavetta della busta **rubati o persi**;
- password o telefono con la verifica in due passaggi in mano a un'altra persona; **accessi che l'utente non
  riconosce** nel registro degli accessi;
- PDF della cartella o esportazione Excel **inviati alla persona sbagliata**, o fogli stampati lasciati in giro;
- virus o **ransomware** sul server o su un PC di reparto; server **irraggiungibile** a lungo senza copia dei dati
  (anche l'indisponibilità è una violazione);
- avviso del FASAS «**Integrità audit log compromessa**».

## Chi avvisare, subito

| Chi | Nome | Telefono |
|---|---|---|
| Amministratore di sistema | [ ] | [ ] |
| Vice amministratore di sistema | [ ] | [ ] |
| Direzione (titolare) | [ ] | [ ] |
| DPO | [ ] | [ ] |

Chiunque se ne accorga avvisa **subito** l'amministratore di sistema o la direzione: **il tempo conta dal momento
in cui la struttura ne viene a conoscenza**, non da quando arriva la comunicazione al DPO.

## Le prime azioni (prima ora)

1. **Contenere** senza cancellare nulla:
   - credenziali: in *Utenti* disattivare l'utente o cambiarne la password; «Reimposta» la verifica in due passaggi;
   - dispositivo perso: cambiare la password dell'utente (chiude le sessioni aperte su tutti i dispositivi) e
     reimpostare la verifica in due passaggi;
   - server compromesso: **scollegare il cavo di rete** (non spegnere, salvo pericolo: si perderebbero tracce utili);
   - account esterni (Backblaze, DuckDNS, router): cambiare la password, controllare la verifica in due passaggi.
2. **Conservare le prove**: annotare ora e fatti; non cancellare registri; in *Impostazioni › Stato del sistema ed
   errori* e nel registro degli accessi esportare quello che serve; nell'audit premere «Verifica integrità catena».
3. **Annotare** la violazione nel registro qui sotto, anche se sembra piccola.

## Entro 72 ore: valutazione e notifica

1. Il DPO, con l'amministratore di sistema, valuta: quali dati, quanti interessati, se i dati erano **cifrati con
   la chiave al sicuro** (es. backup su Backblaze o disco USB: senza la chiave sono illeggibili), conseguenze
   probabili.
2. **Notifica al Garante** entro 72 ore dalla scoperta, con la procedura telematica del sito del Garante, **salvo
   che sia improbabile un rischio** per le persone. Se non tutte le informazioni sono disponibili, si notifica
   comunque e si integra dopo.
3. **Comunicazione agli interessati** (ospiti, tutori, personale) senza ingiustificato ritardo se il rischio è
   **elevato**: linguaggio semplice, cosa è successo, cosa fa la struttura, cosa possono fare.
4. Se c'è un reato (furto, accesso abusivo): denuncia alle autorità.

Contenuto della notifica: natura della violazione, categorie e numero approssimativo di interessati e di
registrazioni, contatti del DPO, conseguenze probabili, misure adottate o proposte.

## Dopo

- Ripristino dei dati se necessario (`docs/BACKUP.md`, «Ripristino vero»; guida d'installazione, «Il server è
  guasto o è stato rubato»).
- Riesame della DPIA e delle misure; formazione se l'errore è organizzativo.

## Registro interno delle violazioni (art. 33, par. 5)

Va tenuto **per ogni violazione**, anche se non notificata.

| N. | Data e ora della scoperta | Chi l'ha scoperta | Cosa è successo | Dati e interessati coinvolti | Misure adottate | Notificata al Garante? (data o motivo del no) | Comunicata agli interessati? | Chiusa il |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
