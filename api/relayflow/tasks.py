import logging
import uuid
from datetime import datetime, timezone

from celery.exceptions import Reject
from sqlalchemy.orm import Session

from relayflow.celery_app import celery_app
from relayflow.config import settings
from relayflow.db import SessionLocal
from relayflow.models import ConsumerControl, Delivery, Event

logger = logging.getLogger(__name__)


class DeliveryFailed(Exception):
    pass


def record(session: Session, event_id: uuid.UUID, consumer: str, attempt: int, status: str, error: str | None) -> None:
    session.add(
        Delivery(
            event_id=event_id,
            consumer=consumer,
            attempt=attempt,
            status=status,
            error=error,
            created_at=datetime.now(timezone.utc),
        )
    )


def perform(event_id: str, consumer: str, attempt: int, final: bool) -> dict:
    with SessionLocal() as session:
        try:
            parsed = uuid.UUID(event_id)
        except ValueError:
            parsed = None
        event = session.get(Event, parsed) if parsed else None
        control = session.get(ConsumerControl, consumer)
        if event is None or control is None:
            if event is not None:
                record(session, event.id, consumer, attempt, "dead", "unknown consumer")
                session.commit()
            raise Reject("unknown event or consumer", requeue=False)
        if control.fail_next:
            status = "dead" if final else "failed"
            record(session, event.id, consumer, attempt, status, "fail switch enabled")
            session.commit()
            logger.info(
                "delivery %s for %s attempt %s",
                status,
                consumer,
                attempt,
                extra={"correlation_id": event.correlation_id},
            )
            raise DeliveryFailed("fail switch enabled")
        record(session, event.id, consumer, attempt, "succeeded", None)
        session.commit()
        logger.info(
            "delivery succeeded for %s attempt %s",
            consumer,
            attempt,
            extra={"correlation_id": event.correlation_id},
        )
        return {
            "event_id": event_id,
            "consumer": consumer,
            "status": "succeeded",
            "correlation_id": event.correlation_id,
        }


@celery_app.task(bind=True, name="relayflow.deliver", max_retries=2, acks_late=True)
def deliver(self, event_id: str) -> dict:
    consumer = (self.request.hostname or "unknown").split("@", 1)[0]
    attempt = self.request.retries + 1
    final = self.request.retries >= self.max_retries
    try:
        return perform(event_id, consumer, attempt, final)
    except Reject:
        raise
    except DeliveryFailed as exc:
        if final:
            raise Reject(str(exc), requeue=False) from exc
        countdown = settings.retry_base_seconds * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=countdown, queue=consumer) from exc
