"""
Protezione delle tabelle quando il database è su Supabase.

Supabase espone lo schema "public" tramite le sue API REST (PostgREST) ai ruoli "anon" e
"authenticated": senza protezioni chiunque abbia la chiave pubblica del progetto potrebbe
leggere le tabelle. FASAS non usa quelle API (accede solo via Django), quindi:
- attiva la Row Level Security su ogni tabella, senza policy => nessun accesso via API;
- revoca ai due ruoli ogni privilegio su tabelle, sequenze e funzioni, anche per le tabelle future.
Django si collega come proprietario delle tabelle e non è soggetto alla RLS.
"""
API_ROLES = ("anon", "authenticated")


def api_roles(cursor):
    cursor.execute("SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", [list(API_ROLES)])
    return [row[0] for row in cursor.fetchall()]


def harden(connection, schema="public"):
    if connection.vendor != "postgresql":
        return {"skipped": "non PostgreSQL"}
    with connection.cursor() as cursor:
        roles = api_roles(cursor)
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tableowner = current_user", [schema]
        )
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f'ALTER TABLE "{schema}"."{table}" ENABLE ROW LEVEL SECURITY')
        if roles:
            grantees = ", ".join(roles)
            cursor.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM {grantees}')
            cursor.execute(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA "{schema}" FROM {grantees}')
            cursor.execute(f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA "{schema}" FROM {grantees}')
            cursor.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" REVOKE ALL ON TABLES FROM {grantees}')
            cursor.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" REVOKE ALL ON SEQUENCES FROM {grantees}')
            cursor.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" REVOKE ALL ON FUNCTIONS FROM {grantees}')
    return {"tables": len(tables), "revoked_roles": roles}


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
