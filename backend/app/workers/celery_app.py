"""
AutoJob AI — Celery App Configuration
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "autojob",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # Re-queue task if worker crashes
    worker_prefetch_multiplier=1,  # One task at a time (important for browser automation)
    task_soft_time_limit=600,  # 10 min soft limit
    task_time_limit=900,  # 15 min hard limit
)

# Auto-discover tasks from workers module
celery_app.autodiscover_tasks(["app.workers"])
