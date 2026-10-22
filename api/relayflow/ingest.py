import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from relayflow.config import settings
from relayflow.models import Event, Intake, Outbox
from relayflow.signatures import signatures_match

logger = logging.getLogger(__name__)

PROVIDERS = {"stripe", "monday", "email"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _duplicate(session: Session, event: Event) -> dict:
    session.add(
        Intake(
            idempotency_key=event.idempotency_key,
            outcome="duplicate",
            event_id=event.id,
            received_at=_now(),
        )
    )
    session.commit()
    logger.info("duplicate webhook", extra={"correlation_id": event.correlation_id})
    return {"status": "duplicate", "event_id": str(event.id), "correlation_id": event.correlation_id}


def accept_webhook(session: Session, provider: str, raw: bytes, signature: str | None) -> dict:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="unknown provider")
    if not signatures_match(settings.webhook_secret, raw, signature):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="body must be json") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="body must be a json object")
    event_type = body.get("type")
    external_id = body.get("id")
    if not isinstance(event_type, str) or not event_type or not isinstance(external_id, str) or not external_id:
        raise HTTPException(status_code=422, detail="payload needs string type and id")
    account = body.get("account") if isinstance(body.get("account"), str) else "demo"
    key = f"{provider}:{event_type}:{external_id}"
    existing = session.scalar(select(Event).where(Event.idempotency_key == key))
    if existing is not None:
        return _duplicate(session, existing)
    correlation_id = uuid.uuid4().hex
    event_id = uuid.uuid4()
    canonical = {
        "id": str(event_id),
        "provider": provider,
        "type": event_type,
        "external_id": external_id,
        "account": account,
        "correlation_id": correlation_id,
        "payload": body,
    }
    event = Event(
        id=event_id,
        provider=provider,
        event_type=event_type,
        external_id=external_id,
        idempotency_key=key,
        raw=body,
        canonical=canonical,
        correlation_id=correlation_id,
        received_at=_now(),
    )
    session.add(event)
    session.add(
        Outbox(
            event_id=event.id,
            routing_key=f"{provider}.{event_type}",
            created_at=_now(),
        )
    )
    session.add(
        Intake(
            idempotency_key=key,
            outcome="accepted",
            event_id=event.id,
            received_at=_now(),
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raced = session.scalar(select(Event).where(Event.idempotency_key == key))
        if raced is None:
            raise
        return _duplicate(session, raced)
    logger.info("accepted webhook", extra={"correlation_id": correlation_id})
    return {"status": "accepted", "event_id": str(event.id), "correlation_id": correlation_id}
