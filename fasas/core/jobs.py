"""Registro dei job periodici: eseguibili da Celery beat o da cron con "manage.py fasas_jobs <nome>"."""
import logging

from django.db import transaction
from django.utils.module_loading import import_string

from fasas.audit.context import audit_context

logger = logging.getLogger("fasas.jobs")

JOBS = {
    "close_shifts": ("fasas.daily.services.auto_close_shifts", "Chiusura automatica dei turni terminati"),
    "protocols": ("fasas.protocols.engine.run_periodic_checks", "Controlli periodici dei protocolli"),
    "appointments": ("fasas.appointments.services.send_reminders", "Promemoria visite (domani / oggi)"),
    "stock": ("fasas.pharmacy.services.stock_alerts", "Farmaci in esaurimento e in scadenza"),
    "documents": ("fasas.documents.services.expiry_alerts", "Documenti in scadenza"),
    "pai_reviews": ("fasas.pai.services.review_reminders", "Scadenze revisioni e verifiche PAI"),
    "reports": ("fasas.reports.services.run_due_schedules", "Generazione report programmati"),
    "report_retention": ("fasas.reports.services.purge_expired_reports", "Eliminazione report oltre la conservazione"),
    "backup": ("fasas.backups.services.scheduled_backup", "Backup cifrato giornaliero e verifica"),
    "audit_verify": ("fasas.audit.services.scheduled_chain_verification", "Verifica integrità audit log"),
    "restore_test": ("fasas.backups.restore_test.scheduled_restore_test", "Prova di ripristino con verbale (trimestrale)"),
    "imports_cleanup": ("fasas.imports.documents.cleanup_stale", "Cancellazione dei file di importazioni non confermate"),
    "cie_cleanup": ("fasas.signatures.cie.cleanup_stale", "Chiusura delle richieste di firma con CIE scadute"),
}


def run_job(name):
    from .monitoring import job_finished, job_started

    path, _ = JOBS[name]
    func = import_string(path)
    job_started(name)
    try:
        with audit_context(user=None, ip="", reason="", source=f"job:{name}"):
            if name in ("backup", "restore_test"):  # gestiscono da sé le transazioni: niente transazione lunga
                result = func()
            else:
                with transaction.atomic():
                    result = func()
    except Exception as exc:
        job_finished(name, exc)
        logger.exception("Job %s fallito", name)
        raise
    job_finished(name)
    logger.info("Job %s completato: %s", name, result)
    return result
