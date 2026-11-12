# Piano del pilota

Un pilota breve e misurato prima di usare il FASAS in tutta la struttura: **un nucleo, 5-8 utenti, 4-6 settimane,
in parallelo al cartaceo**. Lo scopo è scoprire tempi, errori e punti scomodi con poche persone e con il cartaceo
ancora valido, non dimostrare che va tutto bene.

## Prima di iniziare

| Cosa | Chi | Dove |
|---|---|---|
| Adempimenti: DPO, DPIA, nomine, informative, autorizzazioni del personale | direzione | [ADEMPIMENTI_PRIMA_DELL_AVVIO.md](ADEMPIMENTI_PRIMA_DELL_AVVIO.md) |
| Test di penetrazione esterno sulla versione del pilota | soggetto indipendente | [SICUREZZA.md](SICUREZZA.md) |
| Installazione in struttura, backup e prova di ripristino fatta dai referenti | amministratore di sistema | [INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md) |
| Due referenti formati (un coordinatore, un operatore esperto) | direzione | — |
| **Configurazione › Moduli › «Applica la configurazione per il pilota»** | amministratore | nel FASAS |
| Ospiti del nucleo, terapie in corso e checklist di turno inseriti e ricontrollati da due persone | coordinatore | nel FASAS |
| Telefoni Android con l'app FASAS Signer, solo se si usa la CIE | amministratore | [FIRMA_CIE.md](FIRMA_CIE.md) |

## Come si svolge

| Settimane | Cartaceo | FASAS | Obiettivo |
|---|---|---|---|
| 0 | valido | formazione (2 ore a testa) e prova su ospiti di prova | tutti sanno registrare un giro farmaci e chiudere un turno |
| 1-2 | **valido**, si compila tutto | si registra tutto anche nel FASAS | confronto completo: numeri uguali? cosa manca? |
| 3-4 | di riserva (foglio di emergenza) | **valido** | il FASAS regge da solo un turno normale e uno con imprevisti |
| 5-6 | di riserva | valido | conferma; si decide se estendere ad altri nuclei |

Ogni settimana, **30 minuti** tra referenti, coordinatore e chi mantiene il FASAS: indicatori, segnalazioni aperte,
decisioni. Le decisioni si scrivono come risposta nelle segnalazioni (stato «Risolta» o «Non si cambia»).

Durante il pilota non si aggiungono funzioni: solo correzioni di errori e di punti scomodi segnalati.

## Cosa si misura

Nel FASAS: **Archivio e report › Indicatori del pilota** (coordinatore e amministratore), con esportazione CSV.

| Indicatore | Nel FASAS | Sul cartaceo (settimane 1-2) |
|---|---|---|
| Durata del giro farmaci | tempo tra la prima e l'ultima registrazione dello stesso orario (mediana) | inizio e fine annotati a mano su 3 giri al giorno |
| Registrazioni mancanti | dosi programmate senza registrazione alla chiusura del turno | caselle vuote nel foglio terapia |
| Registrazioni in ritardo | registrate oltre 60 minuti dall'orario | — |
| Checklist di turno completate | percentuale alla chiusura | voci non spuntate |
| Segnalazioni | pulsante «Segnala un problema» in alto in ogni pagina | — |

I conteggi di dosi e checklist si fanno **alla chiusura del turno**: se un turno non si chiude, non si conta.

## Quando si va avanti e quando ci si ferma

Si passa alla fase successiva quando, nelle due settimane precedenti:

- le registrazioni mancanti nel FASAS non sono più di quelle del cartaceo;
- il giro farmaci non dura più del 20% rispetto al cartaceo (dalla seconda settimana in poi);
- nessuna segnalazione di tipo «Non funziona» è rimasta aperta più di 3 giorni;
- il backup notturno è riuscito ogni giorno e la prova di ripristino del mese è andata bene.

Ci si ferma subito (si torna al cartaceo, che resta valido) se:

- si perde o si altera una registrazione sanitaria;
- il FASAS non è disponibile per più di un turno;
- un errore del sistema contribuisce a un evento avverso o a un quasi-evento.

Ogni sospensione si annota, con data e motivo, nel registro del pilota tenuto dal coordinatore.

## Alla fine

Un verbale di una pagina firmato da direzione e coordinatore: indicatori del periodo (il CSV), segnalazioni
ricevute e come sono state chiuse, decisione (estendere, ripetere, fermarsi). Solo dopo un esito positivo la
versione del FASAS diventa la **1.0**.
