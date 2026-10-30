"""
Pianificazione automatica dei job FASAS.

Ogni job è una funzione registrata in fasas.core.jobs: Celery beat li esegue
secondo la tabella sotto; in alternativa un cron può lanciare
"python manage.py fasas_jobs <nome>".
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("fasas")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["fasas.core"])

app.conf.beat_schedule = {
    "chiusura-automatica-turni": {"task": "fasas.run_job", "schedule": crontab(minute="*/15"), "args": ("close_shifts",)},
    "protocolli-periodici": {"task": "fasas.run_job", "schedule": crontab(minute="*/30"), "args": ("protocols",)},
    "promemoria-appuntamenti": {"task": "fasas.run_job", "schedule": crontab(minute=5), "args": ("appointments",)},
    "allarmi-magazzino": {"task": "fasas.run_job", "schedule": crontab(hour="6,18", minute=10), "args": ("stock",)},
    "scadenze-documenti": {"task": "fasas.run_job", "schedule": crontab(hour=7, minute=10), "args": ("documents",)},
    "scadenze-pai": {"task": "fasas.run_job", "schedule": crontab(hour=7, minute=0), "args": ("pai_reviews",)},
    "report-programmati": {"task": "fasas.run_job", "schedule": crontab(hour=1, minute=15), "args": ("reports",)},
    "pulizia-report-scaduti": {"task": "fasas.run_job", "schedule": crontab(hour=1, minute=45), "args": ("report_retention",)},
    "backup-giornaliero": {"task": "fasas.run_job", "schedule": crontab(hour=2, minute=30), "args": ("backup",)},
    # prima del backup, così il backup e la sua copia fuori sede contengono il punto di controllo della notte
    "verifica-catena-audit": {"task": "fasas.run_job", "schedule": crontab(hour=2, minute=0), "args": ("audit_verify",)},
    "prova-ripristino-trimestrale": {"task": "fasas.run_job", "args": ("restore_test",),
                                     "schedule": crontab(hour=4, minute=15, day_of_month=1, month_of_year="1,4,7,10")},
    "pulizia-importazioni": {"task": "fasas.run_job", "schedule": crontab(hour=3, minute=50), "args": ("imports_cleanup",)},
    "pulizia-firme-cie": {"task": "fasas.run_job", "schedule": crontab(minute="*/10"), "args": ("cie_cleanup",)},
}
