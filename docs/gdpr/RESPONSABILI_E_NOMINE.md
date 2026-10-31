# Responsabili del trattamento, autorizzati e amministratori di sistema (bozza)

## Fornitori da nominare responsabili (art. 28 GDPR)

Bozza dell'accordo con il fornitore del FASAS: [ACCORDO_ART28_FORNITORE.md](ACCORDO_ART28_FORNITORE.md).

| Fornitore | Ruolo | Cosa verificare nel contratto |
|---|---|---|
| [Hosting del server applicativo] | conserva applicazione, file cifrati, backup locali | sede dei data center in UE, misure di sicurezza, sub-responsabili, notifica delle violazioni entro 24–48 ore, cancellazione a fine contratto |
| [Supabase o altro database gestito] | database PostgreSQL | **regione UE**, DPA del fornitore, sub-responsabili e trasferimenti (clausole contrattuali tipo), backup del fornitore |
| [Archivio dei backup fuori sede] | copia cifrata dei backup | regione UE, immutabilità (object lock), conservazione; i dati arrivano già cifrati |
| [Manutenzione e assistenza del software] | accesso tecnico al sistema | accesso solo quando necessario e tracciato, riservatezza, nomina ad amministratore di sistema |
| [Prestatore della firma qualificata] | firma remota dei medici | qualifica nell'elenco di fiducia europeo; riceve solo l'impronta dei documenti |
| [Servizio email/SMTP] | invio delle notifiche email | le email non contengono dati sanitari |
| [Consulente del lavoro, commercialista] | turni/paghe, rette | solo i dati necessari (export Excel) |

### Installazione su un PC in struttura

| Fornitore | Ruolo | Cosa fare |
|---|---|---|
| Backblaze (B2, regione UE) | responsabile: conserva i backup **già cifrati** | archiviare il DPA per l'UE pubblicato da Backblaze (indicato come parte dei termini di servizio accettati all'iscrizione) con la data di accettazione; con il DPO verificare la base per eventuali accessi dagli USA (Data Privacy Framework o clausole contrattuali tipo) |
| DuckDNS, servizio di controllo, Let's Encrypt | servizi tecnici: nessun dato degli ospiti né del personale | annotarli nel registro (T4) |

Piano completo degli adempimenti: [../ADEMPIMENTI_PRIMA_DELL_AVVIO.md](../ADEMPIMENTI_PRIMA_DELL_AVVIO.md).

## Autorizzati al trattamento (art. 29 e art. 2-quaterdecies Codice privacy)

Ogni utente di FASAS va **autorizzato per iscritto** con l'ambito corrispondente al suo ruolo (operatore,
coordinatore, medico, amministrativo, amministratore di sistema). L'elenco degli utenti attivi è in
*Utenti e permessi*; i permessi personalizzati vanno motivati. Modello: [MODELLO_AUTORIZZAZIONE_PERSONALE.md](MODELLO_AUTORIZZAZIONE_PERSONALE.md).

## Amministratori di sistema (provvedimento del Garante 27 novembre 2008 e s.m.)

- Designazione individuale scritta di chi ha il ruolo *Amministratore* in FASAS e di chi gestisce server e database
  (modello: [MODELLO_NOMINA_AMMINISTRATORE_SISTEMA.md](MODELLO_NOMINA_AMMINISTRATORE_SISTEMA.md)).
- Elenco aggiornato degli amministratori di sistema, comunicato al personale se tratta dati dei lavoratori.
- Registrazione degli accessi degli amministratori (log accessi di FASAS per l'applicazione; [log del server e del
  database a cura del fornitore]) conservata almeno 6 mesi.
- Verifica almeno annuale del loro operato.
