"""Celery application configuration for background worker and periodic scheduler."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "rental_monitoring_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.modules.notifications.tasks",
        "app.workers.scheduled_tasks",
    ],
)

celery_app.conf.update(
    timezone=settings.BUSINESS_TIMEZONE,
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "scan-upcoming-rental-reminders-every-five-minutes": {
            "task": "scheduler.scan_upcoming_reminders",
            "schedule": 300.0,
        },
        "dispatch-pending-outbox-events": {
            "task": "scheduler.process_outbox_events",
            "schedule": 30.0,
        },
    },
)
