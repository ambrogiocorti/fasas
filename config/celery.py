"""
Pianificazione automatica dei job FASAS.

Ogni job è una funzione registrata in fasas.core.jobs: Celery beat li esegue
secondo la tabella SCHEDULE di fasas/core/scheduler.py; in alternativa un cron può lanciare
"python manage.py fasas_jobs <nome>", oppure (versione cloud, senza Redis) gira «manage.py fasas_pianificatore».
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("fasas")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["fasas.core"])

# Orari in fasas/core/scheduler.py, gli stessi del pianificatore integrato della versione cloud
from fasas.core.scheduler import SCHEDULE  # noqa: E402

app.conf.beat_schedule = {
    name: {"task": "fasas.run_job", "schedule": crontab(**spec), "args": (job,)} for name, job, spec in SCHEDULE
}
