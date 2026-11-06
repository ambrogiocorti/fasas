-- FASAS Digitale: protezione delle tabelle dalle API automatiche di Supabase (Data API / PostgREST).
-- Generato da scripts/genera_migrazioni_supabase.py: non modificare a mano.
--
-- Il FASAS legge e scrive solo attraverso il proprio server (Django), collegato come proprietario delle tabelle.
-- Le API REST di Supabase non servono e non devono dare accesso ai dati:
--   1. Row Level Security attiva su ogni tabella dello schema public, senza alcuna policy: via API nessuna riga;
--   2. nessun privilegio ai ruoli delle API (anon, authenticated, service_role) su tabelle, sequenze e funzioni,
--      anche per le tabelle create in futuro.
-- Il FASAS ripete gli stessi passi dopo ogni aggiornamento (fasas/core/supabase.py). È sicuro rieseguire il file.

DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', item.tablename);
    END LOOP;
END
$$;

DO $$
DECLARE
    api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = api_role) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', api_role);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', api_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', api_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', api_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', api_role);
        END IF;
    END LOOP;
END
$$;
