"""
Controlli della versione cloud (FASAS_CLOUD=1, docs/CLOUD.md): all'avvio («migrate» li esegue) fermano il servizio
se manca qualcosa senza cui i dati andrebbero persi o il sito non risponderebbe al dominio.
"""
from django.conf import settings
from django.core.checks import Error, Warning, register


@register("fasas")
def cloud_checks(app_configs=None, **kwargs):
    if not settings.FASAS_CLOUD:
        return []
    problems = []
    database = settings.DATABASES["default"]
    if database["ENGINE"] != "django.db.backends.postgresql":
        problems.append(Error("Nella versione cloud il database è PostgreSQL (Supabase): manca DATABASE_URL.",
                              id="fasas.E101"))
    elif str(database.get("PORT") or "") == "6543":
        problems.append(Warning(
            "DATABASE_URL usa la porta 6543 (pooler in modalità transazione): il backup con pg_dump non funziona. "
            "Usare la stringa «Session pooler» (porta 5432) di Supabase.", id="fasas.W101"))
    if not settings.FASAS_S3_BUCKET and not settings.FASAS_PERSISTENT_DISK:
        problems.append(Error(
            "I file caricati andrebbero persi a ogni riavvio del container: configurare lo storage S3 "
            "(FASAS_S3_BUCKET, FASAS_S3_ENDPOINT_URL, FASAS_S3_REGION, FASAS_S3_ACCESS_KEY, FASAS_S3_SECRET_KEY) "
            "oppure, con un disco persistente montato su /data, FASAS_PERSISTENT_DISK=1.", id="fasas.E102"))
    elif settings.FASAS_S3_BUCKET:
        options = settings.STORAGES["default"].get("OPTIONS", {})
        if not options.get("access_key") or not options.get("secret_key") or not options.get("endpoint_url"):
            problems.append(Error("Storage S3 incompleto: servono FASAS_S3_ENDPOINT_URL, FASAS_S3_ACCESS_KEY e "
                                  "FASAS_S3_SECRET_KEY.", id="fasas.E103"))
    if not settings.FASAS_PUBLIC_HOSTS:
        problems.append(Error("Manca il dominio: FASAS_DOMAIN (es. fasas.miacooperativa.it).", id="fasas.E104"))
    if settings.DEBUG:
        problems.append(Error("DJANGO_DEBUG deve essere 0 nella versione cloud.", id="fasas.E105"))
    if not settings.FASAS_ENCRYPTION_KEYS or not settings.FASAS_BACKUP_KEY:
        problems.append(Error("Mancano le chiavi FASAS_ENCRYPTION_KEYS e FASAS_BACKUP_KEY (manage.py fasas_genkey).",
                              id="fasas.E106"))
    from fasas.backups import offsite

    if not offsite.is_configured() and not settings.FASAS_PERSISTENT_DISK:
        problems.append(Warning(
            "Backup senza copia fuori sede: il disco del container è temporaneo e il backup della notte si perde al "
            "primo riavvio. Configurare FASAS_OFFSITE_* (docs/CLOUD.md, passo 5).", id="fasas.W102"))
    return problems
