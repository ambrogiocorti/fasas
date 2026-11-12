try:
    from .celery import app as celery_app
except ImportError:  # Celery è opzionale: i job girano anche via "manage.py fasas_jobs"
    celery_app = None

__all__ = ("celery_app",)
