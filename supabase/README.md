# Migrazioni SQL per Supabase

Da applicare una volta, nell'ordine, su un progetto Supabase nuovo (guida completa: [docs/CLOUD.md](../docs/CLOUD.md),
passo 2):

1. `migrations/20261106120000_fasas_schema_e_dati_iniziali.sql`: tabelle, vincoli, indici, protezioni dell'audit,
   migrazioni di Django già segnate come eseguite, ruoli e permessi, configurazione iniziale. Nessun dato personale.
2. `migrations/20261106120100_fasas_protezione_api.sql`: Row Level Security su ogni tabella e nessun privilegio ai
   ruoli delle API di Supabase (`anon`, `authenticated`, `service_role`). Si può rieseguire.

Funzionano dall'editor SQL di Supabase, con `psql` e con `supabase db push`. Gli aggiornamenti successivi dello
schema li applica il FASAS da solo a ogni avvio. I file si rigenerano con `python scripts/genera_migrazioni_supabase.py`.
