from celery import shared_task

from .jobs import run_job


@shared_task(name="fasas.run_job")
def run_job_task(name):
    return run_job(name)
