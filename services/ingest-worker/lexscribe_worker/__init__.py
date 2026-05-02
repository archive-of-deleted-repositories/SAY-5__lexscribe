"""Celery ingest pipeline."""

from lexscribe_worker.app import celery_app

__all__ = ["celery_app"]
