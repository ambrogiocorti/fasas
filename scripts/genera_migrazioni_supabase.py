#!/usr/bin/env python3
"""
Genera le migrazioni SQL per Supabase (cartella supabase/migrations) dalle migrazioni di Django.

    python scripts/genera_migrazioni_supabase.py postgres://utente:password@localhost:5432/database_vuoto

Il database indicato deve essere VUOTO e serve solo per generare i file (viene riempito e lasciato così):
1. «manage.py migrate» crea tabelle, vincoli, indici, protezioni dell'audit e dati iniziali (ruoli e permessi,
   configurazione, parametri sanitari, protocolli, checklist, impostazioni delle notifiche);
2. pg_dump scrive tutto come istruzioni SQL eseguibili anche dall'editor SQL di Supabase (niente comandi di psql);
3. si tolgono i dati legati a chi ha generato i file (voci dell'audit, sessioni, stato dei job, errori).

Il secondo file (protezione delle API di Supabase) è fisso e si riscrive uguale ogni volta.
Nessun dato personale o sanitario: il database di partenza è vuoto.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "supabase" / "migrations"
SCHEMA_FILE = "20261106120000_fasas_schema_e_dati_iniziali.sql"
SECURITY_FILE = "20261106120100_fasas_protezione_api.sql"

# dati che dipendono dall'installazione che genera i file: non vanno nelle migrazioni
EXCLUDED_DATA = ["audit_auditlog", "audit_auditlog_id_seq", "audit_auditcheckpoint", "django_session",
                 "core_jobrun", "core_errorevent", "core_keycanary", "accounts_loginattempt"]

HEADER = """-- FASAS Digitale {version}: schema del database e dati iniziali per Supabase (PostgreSQL 15 o 17).
-- Generato da scripts/genera_migrazioni_supabase.py: non modificare a mano.
--
-- Come si applica (una volta, su un progetto Supabase nuovo):
--   - editor SQL di Supabase: incollare questo file ed eseguirlo, poi il file *_fasas_protezione_api.sql;
--   - oppure, con la CLI di Supabase collegata al progetto: «supabase db push».
-- Contiene: {tables} tabelle con vincoli e indici, protezioni dell'audit (sola aggiunta), le {migrations}
-- migrazioni di Django già segnate come eseguite, ruoli e permessi, configurazione iniziale.
-- Nessun dato personale o sanitario, nessun utente: il primo amministratore si crea all'avvio (docs/CLOUD.md).
-- Gli aggiornamenti futuri dello schema li applica il FASAS da solo a ogni avvio («migrate»).

"""

SECURITY = """-- FASAS Digitale: protezione delle tabelle dalle API automatiche di Supabase (Data API / PostgREST).
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
"""

# righe di pg_dump che l'editor SQL di Supabase non accetta o che non servono
DROP_LINES = re.compile(r"^(\\restrict|\\unrestrict|SET transaction_timeout|-- Dumped (from|by) )")


def run(args, env):
    result = subprocess.run(args, env=env, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Errore in {' '.join(args[:3])}:\n{result.stderr[-3000:]}")
    return result.stdout


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    url = sys.argv[1]
    env = dict(os.environ, DATABASE_URL=url, DJANGO_DEBUG="1", FASAS_CLOUD="0", FASAS_S3_BUCKET="")
    env.pop("DJANGO_SETTINGS_MODULE", None)
    tables_before = run(["psql", url, "-Atc", "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"], env)
    if tables_before.strip() != "0":
        sys.exit("Il database non è vuoto: serve un database nuovo, solo per generare i file.")
    run([sys.executable, "manage.py", "migrate", "--noinput"], env)
    # tutto il database (nuovo, quindi solo lo schema public); senza «--schema», che farebbe ricreare lo schema
    dump = run(["pg_dump", url, "--no-owner", "--no-privileges", "--column-inserts", "--rows-per-insert=200",
                *[f"--exclude-table-data={name}" for name in EXCLUDED_DATA]], env)
    lines = [line for line in dump.splitlines() if not DROP_LINES.match(line)]
    text = "\n".join(lines).strip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    tables = run(["psql", url, "-Atc", "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"], env).strip()
    migrations = run(["psql", url, "-Atc", "SELECT count(*) FROM django_migrations"], env).strip()
    version = run([sys.executable, "-c", "import fasas; print(fasas.__version__)"], env).strip()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / SCHEMA_FILE).write_text(
        HEADER.format(version=version, tables=tables, migrations=migrations)
        + text + "\n-- percorso di ricerca di nuovo quello normale per le istruzioni successive\nRESET search_path;\n",
        encoding="utf-8")
    (OUT / SECURITY_FILE).write_text(SECURITY, encoding="utf-8")
    print(f"Scritti {SCHEMA_FILE} ({tables} tabelle, {migrations} migrazioni) e {SECURITY_FILE} in {OUT}")


if __name__ == "__main__":
    main()
