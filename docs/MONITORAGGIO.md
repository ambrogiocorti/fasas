# Monitoraggio

Il FASAS si controlla da solo e avvisa l'amministratore; un servizio esterno, anche gratuito, può controllare che il
sito risponda.

## Controllo di salute: `/salute/`

- Senza credenziali risponde `{"status": "ok" | "degraded" | "error", "version": "…"}`: **503** se il database o i
  dischi non funzionano o se le chiavi di cifratura non sono quelle giuste, 200 negli altri casi.
- Con `FASAS_HEALTH_TOKEN` (intestazione `Authorization: Bearer <token>` oppure `?token=`) mostra anche il dettaglio:
  database, chiavi, cartelle, spazio su disco (`FASAS_HEALTH_MIN_FREE_GB`), ultimo backup e copia fuori sede,
  verifica dell'audit, job in ritardo o falliti, errori delle ultime 24 ore. Nessun dato sanitario.

Configurare un servizio di controllo (es. Uptime Kuma, open source, installabile su un altro server) che chiami
`https://<dominio>/salute/` ogni 5 minuti e avvisi via email o telefono se la risposta non è 200.

## Job periodici

Ogni job registra avvio, fine ed esito. Se cron o Celery si fermano, `/salute/` segnala i job «in ritardo» (oltre
il doppio dell'intervallo previsto più mezz'ora). Elenco e intervalli in *Impostazioni › Stato del sistema ed errori*.

## Registro errori

Gli errori delle pagine e dei job finiscono in *Impostazioni › Stato del sistema ed errori*, raggruppati per punto del
codice. Per riservatezza non si salvano messaggi, valori, parametri né indirizzi completi: solo tipo d'errore, rotta
(es. `GET ospiti/<int:pk>/`) e righe del codice. L'amministratore riceve una notifica alla 1ª, 10ª, 100ª e 1000ª
occorrenza; il dettaglio tecnico completo è nel registro del server alla stessa ora.

## Chiavi

`python manage.py fasas_chiavi verifica` controlla che le chiavi configurate aprano i dati e ne stampa le impronte,
da confrontare con il foglio di custodia.
