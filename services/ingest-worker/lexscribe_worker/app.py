"""Celery app — three queues with hard concurrency caps.

Why three queues instead of one prioritised queue?

* Each stage has a different upstream dependency: ``parse`` is CPU-bound on
  PDF parsing, ``embed`` is network-bound on the embedding provider, and
  ``classify`` shares the LLM provider's rate limits with the QA path. Mixing
  them in one queue makes a slow stage starve a fast one.
* The Redis semaphore around ``embed`` lives outside Celery's prefetch logic
  precisely so we can throttle network use without surrendering a worker slot.
"""

from __future__ import annotations

from celery import Celery
from lexscribe_shared.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "lexscribe",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="parse",
    task_queues={
        "parse": {"exchange": "parse", "routing_key": "parse"},
        "embed": {"exchange": "embed", "routing_key": "embed"},
        "classify": {"exchange": "classify", "routing_key": "classify"},
    },
    task_routes={
        "lexscribe_worker.tasks.parse_pdf": {"queue": "parse"},
        "lexscribe_worker.tasks.chunk": {"queue": "parse"},
        "lexscribe_worker.tasks.embed": {"queue": "embed"},
        "lexscribe_worker.tasks.classify_spans": {"queue": "classify"},
    },
    timezone="UTC",
    enable_utc=True,
)


# Auto-discover tasks
import lexscribe_worker.tasks  # noqa: E402, F401
