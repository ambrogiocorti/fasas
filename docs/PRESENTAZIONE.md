# Presentazione online del FASAS (dati inventati)

Una copia del FASAS su internet per mostrarlo e farlo provare. Stesso programma della versione locale, con **ospiti,
terapie e documenti inventati**. Non serve nessun database, nessuno storage e nessuna chiave da configurare.

**Mai dati di persone reali**: le chiavi di cifratura sono quelle pubbliche di prova e le password degli utenti sono
scritte nella pagina di accesso. Per l'uso vero c'è [FASAS_ONLINE.md](FASAS_ONLINE.md).

## Dove pubblicarla senza carta di credito (verifica di novembre 2026)

| Servizio | Carta | Indirizzo | Per cosa |
|---|---|---|---|
| **PythonAnywhere**, account gratuito (consigliato) | no | `nomeutente.eu.pythonanywhere.com` (server in UE) | presentazione sempre raggiungibile, da far provare anche ad altri |
| **GitHub Codespaces** | no | indirizzo temporaneo `…app.github.dev` | presentazione dal vivo, acceso solo mentre lo usi |
| Render (`render.yaml` di questo repository) | a volte richiesta | `fasas.online` | se la carta viene accettata: passo «Render» in fondo |

Il piano gratuito di PythonAnywhere non permette un dominio proprio: `fasas.online` si fa rimandare all'indirizzo di
PythonAnywhere (passo A4).

## A. PythonAnywhere (gratuito, senza carta)

1. **Account**: <https://eu.pythonanywhere.com> › *Pricing & signup* › **Create a Beginner account** (nome utente,
   email, password). Il nome utente diventa l'indirizzo: `nomeutente.eu.pythonanywhere.com`.
2. **Sito vuoto**: scheda **Web** › **Add a new web app** › Next › **Manual configuration** › **Python 3.13** (o la
   più recente in elenco) › Next.
3. **Installazione**: scheda **Consoles** › **Bash**, poi incollare:

   ```bash
   git clone --depth 1 https://github.com/ambrogiocorti/fasas.git && cd fasas && ./scripts/presentazione_pythonanywhere.sh
   ```

   In qualche minuto installa le librerie, crea i dati di esempio e collega il sito. Alla fine scrive tre impostazioni
   da controllare nella scheda **Web**: *Python version* (la stessa scelta al punto 2), *Virtualenv*
   (`/home/nomeutente/.virtualenvs/fasas`) e **Force HTTPS** su *Enabled*. Poi il pulsante verde **Reload**.
4. **fasas.online** (facoltativo): nel repository `fasas-deploy`, che oggi pubblica `fasas.online` con GitHub Pages,
   aggiungere il file `index.html`:

   ```html
   <!doctype html><meta charset="utf-8"><title>FASAS Digitale</title>
   <meta http-equiv="refresh" content="0; url=https://nomeutente.eu.pythonanywhere.com/">
   <a href="https://nomeutente.eu.pythonanywhere.com/">FASAS Digitale – presentazione</a>
   ```

   Così chi apre `fasas.online` arriva alla presentazione (nella barra degli indirizzi compare quello di PythonAnywhere).

Da sapere:

- l'account gratuito tiene acceso il sito per un mese: scheda **Web** › **Run until 1 month from today**, una volta al
  mese (arriva un'email di promemoria);
- i dati inseriti restano; per tornare ai dati di esempio con le date di oggi (per esempio prima di una presentazione):
  console Bash › `cd fasas && ./scripts/presentazione_pythonanywhere.sh --rigenera`, poi **Reload**;
- per aggiornare alla versione più recente: `cd fasas && git pull && ./scripts/presentazione_pythonanywhere.sh`;
- niente job pianificati (promemoria e chiusura automatica dei turni non partono da soli): per mostrare il programma
  non servono.

## B. GitHub Codespaces (per la presentazione dal vivo)

1. Su GitHub, repository `fasas` › **Code** › **Codespaces** › **Create codespace**. Parte da solo con i dati di
   esempio (2–3 minuti la prima volta) e apre la scheda del FASAS.
2. Per farlo vedere ad altri: in basso scheda **Porte** › porta 8000 › tasto destro › **Port visibility** › **Public**,
   e condividere l'indirizzo.
3. Si spegne dopo 30 minuti senza uso (o quando lo si chiude); le ore gratuite al mese bastano per molte presentazioni.

## Render (se la carta viene accettata)

1. <https://render.com> con l'account GitHub › **New** › **Blueprint** › repository `ambrogiocorti/fasas` ›
   **Apply**: legge `render.yaml`, non c'è nulla da compilare.
2. Settings › **Custom Domains**: `fasas.online` e `www.fasas.online`; su Register.it togliere i 4 record A di GitHub
   Pages (`185.199.108–111.153`) e mettere i record indicati da Render; su `fasas-deploy` › Settings › Pages togliere il
   dominio.

Come si comporta su Render:

| | |
|---|---|
| Costo | piano Free di Render: nessun costo |
| Dopo 15 minuti senza visite | il servizio si addormenta; la prima pagina dopo la pausa arriva in circa un minuto. **Aprire il link qualche minuto prima della presentazione** |
| A ogni risveglio o aggiornamento | i dati tornano quelli di esempio, con le date di oggi: quello che si è inserito sparisce |
| Utenti | admin, coordinatore, operatore, medico, amministrativo (password nella pagina di accesso); niente verifica in due passaggi, per entrare subito |
| Aggiornamenti | a ogni modifica del ramo su GitHub Render ricostruisce e ripubblica da solo |
| Non attivi | backup, copia fuori sede, firma con CIE reale, notifiche push sul telefono |

Per una presentazione riservata: Render › servizio › **Environment** › aggiungere `FASAS_PRESENTAZIONE_PASSWORD` con una
password scelta (almeno 10 caratteri). Al riavvio successivo gli utenti di prova usano quella e la pagina di accesso
non la mostra più.

## Altri servizi

Va bene qualsiasi servizio che avvii il `Dockerfile` di questo repository con la variabile `FASAS_PRESENTAZIONE=1`
(porta nella variabile `PORT`, controllo di salute `/salute/`): non servono altre impostazioni (a novembre 2026 Koyeb, Oracle e Google Cloud Run chiedono la carta e Hugging Face
fa pagare gli spazi Docker).

## Provarla sul proprio PC

```bash
docker build -t fasas . && docker run --rm -p 8000:8000 -e FASAS_PRESENTAZIONE=1 -e DJANGO_SECURE_SSL_REDIRECT=0 fasas
```

poi aprire `http://localhost:8000`. Senza Docker resta l'avvio di prova di sempre (`avvia.bat` o `./avvia.sh`).
