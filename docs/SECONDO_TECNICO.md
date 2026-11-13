# Guida per il secondo tecnico

Il FASAS non deve dipendere da una sola persona. Questa pagina serve a **chi sostituisce lo sviluppatore** (un
tecnico della cooperativa o un professionista esterno): cosa c'è, dove si trova, come si aggiorna, come si ripristina
e cosa non va mai fatto. Si legge in un'ora; le procedure si provano almeno una volta **prima** che servano.

## Cosa serve sapere già

Linux da riga di comando, Docker e docker compose, Git, nozioni di PostgreSQL. Non serve conoscere Django per
aggiornare e ripristinare; serve per correggere il codice.

## Dove sono le cose

| Cosa | Dove |
|---|---|
| Codice | repository Git (`ambrogiocorti/fasas`), branch indicato da chi ha consegnato il FASAS |
| Server | PC in struttura, Ubuntu Server con disco cifrato ([INSTALLAZIONE_IN_STRUTTURA.md](INSTALLAZIONE_IN_STRUTTURA.md)); nella versione cloud servizio di hosting + Supabase ([CLOUD.md](CLOUD.md)) |
| Configurazione e chiavi | file `.env` sul server; copia nella **busta di custodia** in cassaforte (passo 11 della guida) |
| Chiave di firma dell'app Android | file `fasas-signer.jks` e password: busta di custodia ([FIRMA_CIE.md](FIRMA_CIE.md), «Distribuire l'app») |
| Backup | ogni notte cifrato sul server, copia fuori sede (Backblaze B2), copia mensile su USB, disco di continuità ogni 5 minuti ([BACKUP.md](BACKUP.md)) |
| Accesso da casa | VPN del gestore del sistema, facoltativa (passo 15c) |
| Controllo dall'esterno | servizio gratuito sulla pagina `/salute/` (passo 16) |
| Errori | nel FASAS: Sistema › Errori del sistema; sul server `docker compose logs` |

## Ogni mese (30 minuti)

1. Nel FASAS, **Pannello di sistema**: nessun avviso rosso (backup, verifica dell'audit, protocolli non validati).
2. Aggiornamento: `sudo ./scripts/aggiorna_fasas.sh` (backup prima, contenitori aggiornati, controllo dopo).
3. Copia su disco USB: `sudo ./scripts/copia_backup_usb.sh`; il disco torna in cassaforte.
4. **Segnalazioni** del pilota (Da controllare › Segnalazioni): rispondere e chiudere quelle risolte.

Ogni tre mesi la **prova di ripristino** parte da sola e lascia un verbale (Sistema › Backup): leggerlo. Una volta
l'anno ripristinare a mano su un PC di prova, seguendo [BACKUP.md](BACKUP.md).

## Quando qualcosa non va

| Sintomo | Cosa fare |
|---|---|
| Il FASAS non si apre in struttura | `docker compose ps` e `docker compose logs --tail 100 web`; riavvio: `docker compose up -d` |
| Non si apre da fuori ma in struttura sì | DuckDNS e inoltro delle porte del router (passi 6-7) |
| Cade la corrente | il gruppo di continuità spegne il server in ordine; al ritorno parte da solo. Controllare il pannello di sistema |
| Si guasta il server | nuovo PC, guida di installazione, poi ripristino dall'ultimo backup con le chiavi della busta |
| Avviso «audit non integro» | **non correggere a mano**: annotare data e ora, avvisare direzione e DPO, seguire [SICUREZZA.md](SICUREZZA.md) |
| Sospetta violazione di dati | procedura delle 72 ore ([gdpr/PROCEDURA_VIOLAZIONI.md](gdpr/PROCEDURA_VIOLAZIONI.md)) |

Durante un'interruzione il personale lavora con la modalità senza rete e il foglio di emergenza
([PIANO_DI_CONTINUITA.md](PIANO_DI_CONTINUITA.md)); poi si riapre il turno e si trascrive.

## Cosa non va mai fatto

- Rigenerare le chiavi del `.env`: i documenti e i backup cifrati non si leggerebbero più.
- Modificare o cancellare righe del database a mano: l'audit lo rileva e i dati perdono valore.
- Ripristinare un backup **sopra** il database in uso senza averlo provato prima su una copia.
- Pubblicare un'app Android firmata con una chiave diversa da quella della struttura.
- Accendere la firma con il PIN della carta, le interazioni o altri promemoria clinici senza il parere previsto
  ([FIRMA_CIE.md](FIRMA_CIE.md), [DISPOSITIVO_MEDICO.md](DISPOSITIVO_MEDICO.md)).

## Passaggio di consegne

Da fare insieme allo sviluppatore, con un verbale firmato:

- [ ] accesso al repository e al server (utente proprio, non condiviso);
- [ ] lettura insieme della busta di custodia (si richiude e si firma la nuova chiusura);
- [ ] un aggiornamento eseguito dal secondo tecnico;
- [ ] un ripristino completo su un PC di prova eseguito dal secondo tecnico;
- [ ] contatti: sviluppatore, DPO, referente della struttura, fornitore di internet.
