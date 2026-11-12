# Passaggio dal FASAS cartaceo

L'obiettivo non è ricopiare tutto: si inseriscono i **dati in corso** (quelli che servono dal primo giorno)
e si **scansiona lo storico**. In una comunità di 20–30 ospiti il passaggio richiede in genere da due a quattro
giornate di lavoro di una persona, più la verifica delle terapie da parte del medico.

Menu **Struttura → Importa dal cartaceo** (coordinatore sanitario).

## 1. Preparazione

1. **Data di passaggio**: scegliete un giorno (es. il primo del mese). Fino al giorno prima si scrive sul cartaceo,
   da quel giorno solo su FASAS Digitale. Evitate i periodi con molti ingressi o dimissioni.
2. **Configurazione**: prima dell'importazione controllate *Configurazione* (turni, evacuazioni, blocco modifiche),
   i tag clinici e i tipi di parametro.
3. **Utenti**: create gli account di operatori, coordinatori e medici.

## 2. Dati in corso – modello Excel

Scaricate il modello da *Importa dal cartaceo → Scarica il modello Excel*. Ogni foglio ha le intestazioni già pronte,
le colonne obbligatorie in rosso, gli elenchi a scelta e un commento di aiuto su ogni intestazione.

| Foglio | Da dove prendere i dati |
|---|---|
| Ospiti | frontespizio / scheda anagrafica del FASAS |
| Contatti | scheda familiari, decreto di nomina di tutore o amministratore di sostegno |
| Diagnosi | ultima relazione medica, scheda sanitaria |
| Allergie | scheda sanitaria (per i farmaci scrivete il **principio attivo**) |
| Terapie | **foglio unico di terapia** in vigore, firmato dal medico |
| Magazzino | inventario dei farmaci alla data di passaggio (lotto, scadenza, quantità) |

Consigli:

- Il **codice fiscale** collega i fogli: è controllato anche il carattere finale; un avviso indica un probabile
  errore di battitura.
- Orari delle terapie: `08:00, 13:00, 20:00` (vanno bene anche `8, 13, 20`). Vuoto per i farmaci al bisogno.
- Dosi con decimali: `0,5`. Date: `GG/MM/AAAA`.
- I farmaci non ancora in anagrafica vengono creati con nome, dosaggio e principio attivo indicati.

### Caricamento e anteprima

1. Caricate il file: il sistema lo controlla **senza salvare nulla** e mostra quante voci verranno inserite,
   gli **errori** riga per riga (bloccanti) e gli **avvisi** da controllare (es. farmaci nuovi in anagrafica,
   duplicati di principio attivo, interazioni, allergie al farmaco).
2. Correggete il file e ricaricatelo finché non restano errori. Si può anche importare un foglio per volta.
3. Confermate. L'importazione è *tutto o niente*: o entra tutto il file o niente.
4. Ogni dato inserito compare nell'audit log con origine **import**, l'utente e il nome del file.
   Il file caricato viene cancellato appena l'importazione è conclusa o annullata.

Ricaricare lo stesso file è sicuro: ospiti, contatti, diagnosi, allergie, terapie e lotti già presenti
vengono riconosciuti e **saltati**, non duplicati. Gli ospiti già presenti non vengono modificati.

### Dopo l'importazione

- Il **medico** apre *Terapie in corso* e confronta ogni terapia con il foglio unico cartaceo prima del primo
  giro farmaci.
- Completate i tag clinici nuovi (colore, avviso per gli operatori) e i PAI.

## 3. Storico – documenti scansionati

Diari, parametri, eventi, consensi, referti e PAI degli anni precedenti **non si ricopiano**: si scansionano in PDF
(un file per documento, 200–300 dpi, bianco e nero o scala di grigi) e si caricano come documenti della cartella.

Il sistema abbina ogni file all'ospite leggendo il nome:

```
RSSMRA80A01F205X consenso informato.pdf      ← codice fiscale nel nome
Rossi Mario - referto neurologico 2023.pdf   ← cognome e nome all'inizio
Rossi Mario/diario 2024.pdf                  ← cartella con cognome e nome (dentro uno ZIP)
```

Si possono caricare più file insieme o un archivio ZIP. In anteprima si vede l'abbinamento di ogni file e si possono
correggere ospite e titolo, o togliere la spunta ai file da non caricare. I file restano cifrati in un'area
temporanea fino alla conferma (e vengono cancellati dopo 48 ore se l'anteprima viene abbandonata).

Per scansioni molto numerose, dal server:

```bash
python manage.py fasas_import_documenti /percorso/scansioni --utente coordinatore --categoria other
python manage.py fasas_import_documenti /percorso/scansioni --utente coordinatore --categoria other --conferma
```

La prima riga mostra solo l'abbinamento; con `--conferma` carica. Allo stesso modo il file Excel:

```bash
python manage.py fasas_import fasas.xlsx --utente coordinatore             # anteprima
python manage.py fasas_import fasas.xlsx --utente coordinatore --conferma  # importazione
```

## 4. Il cartaceo dopo il passaggio

Il FASAS cartaceo chiuso va **conservato** secondo i tempi previsti per la documentazione sanitaria e sociosanitaria
della vostra regione: la scansione ne facilita la consultazione ma non lo sostituisce, salvo procedura di
dematerializzazione conforme (vedi [GDPR e verifiche](gdpr/CHECKLIST_ATS.md)).
