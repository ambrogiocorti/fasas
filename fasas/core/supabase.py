"""
Protezione delle tabelle quando il database è su Supabase.

Supabase espone lo schema "public" tramite le sue API REST (PostgREST) ai ruoli "anon" e
"authenticated": senza protezioni chiunque abbia la chiave pubblica del progetto potrebbe
leggere le tabelle. FASAS non usa quelle API (accede solo via Django), quindi:
- attiva la Row Level Security su ogni tabella del FASAS, senza policy => nessun accesso via API;
- revoca ai ruoli delle API ogni privilegio su tabelle, sequenze e funzioni del FASAS e, in un database dedicato,
  anche per le tabelle future;
  anche a "service_role": se la sua chiave segreta finisse fuori, le API non darebbero comunque i dati del FASAS.
Django si collega come proprietario delle tabelle e non è soggetto alla RLS.
Le stesse istruzioni sono in supabase/migrations/*_fasas_protezione_api.sql per chi prepara il database a mano.
Il FASAS va in un database (progetto Supabase) dedicato: con tabelle di altre applicazioni nello stesso schema la
versione cloud non parte (fasas/core/cloud.py) e qui non si tocca nulla che non sia del FASAS.
"""
API_ROLES = ("anon", "authenticated", "service_role")
# tabelle di Django che non corrispondono a un modello
EXTRA_TABLES = {"django_migrations"}


def api_roles(cursor):
    cursor.execute("SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", [list(API_ROLES)])
    return [row[0] for row in cursor.fetchall()]


def fasas_tables(connection):
    """Tabelle dei modelli del FASAS (e di Django) nel database."""
    return set(connection.introspection.django_table_names(include_views=False)) | EXTRA_TABLES


def foreign_tables(connection, schema="public"):
    """Tabelle dello schema che non sono del FASAS: in un database dedicato l'elenco è vuoto."""
    if connection.vendor != "postgresql":
        return []
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", [schema])
        present = {row[0] for row in cursor.fetchall()}
    return sorted(present - fasas_tables(connection))


def harden(connection, schema="public"):
    """
    Protegge solo tabelle, sequenze e funzioni del FASAS. I privilegi predefiniti dello schema (tabelle future) si
    cambiano solo se il database è dedicato: in un database condiviso non si tocca nulla di altre applicazioni.
    """
    if connection.vendor != "postgresql":
        return {"skipped": "non PostgreSQL"}
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        roles = api_roles(cursor)
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tableowner = current_user", [schema]
        )
        tables = sorted({row[0] for row in cursor.fetchall()} & fasas_tables(connection))
        for table in tables:
            cursor.execute(f"ALTER TABLE {quote(schema)}.{quote(table)} ENABLE ROW LEVEL SECURITY")
        foreign = foreign_tables(connection, schema)
        if roles:
            grantees = ", ".join(quote(role) for role in roles)
            for table in tables:
                cursor.execute(f"REVOKE ALL ON TABLE {quote(schema)}.{quote(table)} FROM {grantees}")
            # sequenze delle chiavi primarie delle stesse tabelle (colonne identity o serial)
            cursor.execute(
                "SELECT DISTINCT seq.relname FROM pg_class seq JOIN pg_depend dep ON dep.objid = seq.oid "
                "JOIN pg_class tab ON tab.oid = dep.refobjid JOIN pg_namespace ns ON ns.oid = seq.relnamespace "
                "WHERE seq.relkind = 'S' AND dep.deptype IN ('a', 'i') AND ns.nspname = %s AND tab.relname = ANY(%s)",
                [schema, tables],
            )
            for (sequence,) in cursor.fetchall():
                cursor.execute(f"REVOKE ALL ON SEQUENCE {quote(schema)}.{quote(sequence)} FROM {grantees}")
            cursor.execute(
                "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace "
                "WHERE ns.nspname = %s AND p.proname LIKE 'fasas\\_%%'", [schema],
            )
            for (function,) in cursor.fetchall():
                cursor.execute(f"REVOKE ALL ON FUNCTION {function} FROM {grantees}")
            if not foreign:
                for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                    cursor.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quote(schema)} REVOKE ALL ON {kind} "
                                   f"FROM {grantees}")
    return {"tables": len(tables), "revoked_roles": roles, "foreign_tables": len(foreign)}


def post_migrate_setup(sender, using="default", verbosity=1, **kwargs):
    """
    Dopo ogni migrate (al segnale dell'ultima app, quando esistono tutti i permessi):
    inizializza ruoli e configurazioni e protegge anche le tabelle appena create.
    """
    from django.apps import apps
    from django.core.management import call_command
    from django.db import connections

    # il segnale arriva solo alle app con modelli: si agisce sull'ultima, quando tutti i permessi esistono
    last = [config for config in apps.get_app_configs() if config.models_module is not None][-1]
    if sender.name != last.name:
        return
    harden(connections[using])
    if using == "default":
        import io

        call_command("fasas_setup", stdout=io.StringIO() if verbosity < 2 else None)
