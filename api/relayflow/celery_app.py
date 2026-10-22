from celery import Celery
from celery.signals import worker_ready

from relayflow.broker.topology import WORK_QUEUES, declare_topology
from relayflow.config import settings

celery_app = Celery(
    "relayflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["relayflow.tasks"],
)
celery_app.conf.update(
    task_queues=WORK_QUEUES,
    task_default_exchange="relayflow.events",
    task_default_exchange_type="topic",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_create_missing_queues=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)


def open_topology() -> None:
    with celery_app.connection() as connection:
        declare_topology(connection.channel())


@worker_ready.connect
def declare_on_worker_ready(sender, **kwargs) -> None:
    with sender.app.connection() as connection:
        declare_topology(connection.channel())
