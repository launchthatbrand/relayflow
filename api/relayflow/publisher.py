import logging
from datetime import datetime, timezone

from sqlalchemy import select

from relayflow.broker.topology import events
from relayflow.celery_app import celery_app
from relayflow.db import SessionLocal
from relayflow.models import Outbox

logger = logging.getLogger(__name__)


def publish_pending(limit: int = 50) -> int:
    published = 0
    while published < limit:
        with SessionLocal() as session:
            row = session.scalars(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return published
            celery_app.send_task(
                "relayflow.deliver",
                args=[str(row.event_id)],
                exchange=events,
                routing_key=row.routing_key,
            )
            row.published_at = datetime.now(timezone.utc)
            session.commit()
            logger.info("published %s", row.routing_key)
            published += 1
    return published
