"""Utility SQL specifiche di PostgreSQL usate dalle migrazioni."""

BLOCK_FUNCTION = """
CREATE OR REPLACE FUNCTION fasas_block_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'FASAS: la tabella % e'' in sola aggiunta: % non consentito', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def append_only_operations(table):
    """RunPython che rende una tabella append-only su PostgreSQL (no UPDATE/DELETE/TRUNCATE)."""

    def forwards(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        schema_editor.execute(BLOCK_FUNCTION, params=None)
        schema_editor.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION fasas_block_modification();"
        )
        schema_editor.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION fasas_block_modification();"
        )

    def backwards(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};")

    return forwards, backwards
