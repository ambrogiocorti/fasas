# Presentazione online del FASAS (dati inventati)

Una copia del FASAS su internet, all'indirizzo `fasas.online`, per mostrarlo e farlo provare. Stesso programma della
versione locale, con **ospiti, terapie e documenti inventati** che si ricreano da soli a ogni avvio. Non serve
nessun database, nessuno storage e nessuna chiave: il servizio gratuito di Render costruisce e avvia tutto da GitHub.

**Mai dati di persone reali**: le chiavi di cifratura sono quelle pubbliche di prova e le password degli utenti sono
scritte nella pagina di accesso. Per l'uso vero c'è [FASAS_ONLINE.md](FASAS_ONLINE.md).

## Passo 1 – Pubblicarla (5 minuti, poi 5–10 minuti di attesa)

1. Entrare su <https://render.com> con l'account GitHub.
2. **New** › **Blueprint** › scegliere il repository `ambrogiocorti/fasas` › **Apply**. Non c'è niente da compilare:
   legge il file `render.yaml` (servizio `fasas-presentazione`, piano Free, Francoforte).
3. Aspettare lo stato **Live** (la prima volta costruisce l'immagine: 5–10 minuti).
4. Aprire l'indirizzo mostrato da Render (tipo `https://fasas-presentazione.onrender.com`): pagina di accesso con la
   fascia rossa «Versione di presentazione», utenti e password.

## Passo 2 – Collegare fasas.online

1. Su Render › servizio `fasas-presentazione` › **Settings** › **Custom Domains**: `fasas.online` e
   `www.fasas.online` sono già elencati; accanto Render indica i record DNS da creare.
2. Su Register.it › Domini › `fasas.online` › **Gestione DNS**:
   - togliere i 4 record A `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` (GitHub Pages);
   - creare il record A di `fasas.online` con l'indirizzo indicato da Render;
   - cambiare il CNAME di `www` (oggi `ambrogiocorti.github.io`) con il valore indicato da Render.
3. Su GitHub › `fasas-deploy` › Settings › **Pages**: togliere il dominio `fasas.online`.
4. Su Render premere **Verify** accanto ai due domini: quando risultano verificati, il certificato HTTPS arriva da
   solo (di solito minuti, a volte qualche ora per la propagazione del DNS).

## Come si comporta

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

## Se Render non funziona

Va bene qualsiasi servizio che avvii il `Dockerfile` di questo repository con la variabile `FASAS_PRESENTAZIONE=1`
(porta nella variabile `PORT`, controllo di salute `/salute/`): non servono altre impostazioni.

## Provarla sul proprio PC

```bash
docker build -t fasas . && docker run --rm -p 8000:8000 -e FASAS_PRESENTAZIONE=1 -e DJANGO_SECURE_SSL_REDIRECT=0 fasas
```

poi aprire `http://localhost:8000`. Senza Docker resta l'avvio di prova di sempre (`avvia.bat` o `./avvia.sh`).
