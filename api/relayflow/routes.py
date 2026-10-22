import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from relayflow.broker.topology import queue_depths
from relayflow.celery_app import celery_app
from relayflow.config import settings
from relayflow.db import SessionLocal, get_session
from relayflow.ingest import accept_webhook
from relayflow.models import ConsumerControl, Delivery, Event, Intake, Outbox
from relayflow.signatures import sign

router = APIRouter(prefix="/api")


class SampleIn(BaseModel):
    provider: str
    payload: dict


class FailSwitch(BaseModel):
    fail_next: bool


def _iso(value: datetime) -> str:
    return value.isoformat()


def _deliveries_for(session: Session, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Delivery]]:
    if not event_ids:
        return {}
    rows = session.scalars(
        select(Delivery).where(Delivery.event_id.in_(event_ids)).order_by(Delivery.created_at)
    ).all()
    grouped: dict[uuid.UUID, list[Delivery]] = {}
    for row in rows:
        grouped.setdefault(row.event_id, []).append(row)
    return grouped


def _event_body(event: Event, deliveries: list[Delivery]) -> dict:
    latest: dict[str, dict] = {}
    history = []
    for row in deliveries:
        item = {
            "consumer": row.consumer,
            "attempt": row.attempt,
            "status": row.status,
            "error": row.error,
            "created_at": _iso(row.created_at),
        }
        history.append(item)
        latest[row.consumer] = item
    return {
        "id": str(event.id),
        "provider": event.provider,
        "type": event.event_type,
        "external_id": event.external_id,
        "correlation_id": event.correlation_id,
        "received_at": _iso(event.received_at),
        "raw": event.raw,
        "canonical": event.canonical,
        "consumers": latest,
        "deliveries": history,
    }


def _load_event(session: Session, event_id: str) -> Event:
    try:
        parsed = uuid.UUID(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc
    event = session.get(Event, parsed)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(select(1))
    return {"status": "ok"}


@router.post("/webhooks/{provider}")
async def webhook(provider: str, request: Request) -> dict:
    raw = await request.body()
    with SessionLocal() as session:
        return accept_webhook(session, provider, raw, request.headers.get("x-relay-signature"))


@router.post("/samples")
def create_sample(sample: SampleIn, session: Session = Depends(get_session)) -> dict:
    raw = json.dumps(sample.payload, separators=(",", ":")).encode()
    return accept_webhook(session, sample.provider, raw, sign(settings.webhook_secret, raw))


@router.get("/events")
def list_events(limit: int = 50, session: Session = Depends(get_session)) -> dict:
    bounded = min(max(limit, 1), 100)
    events = session.scalars(select(Event).order_by(Event.received_at.desc()).limit(bounded)).all()
    grouped = _deliveries_for(session, [event.id for event in events])
    return {"events": [_event_body(event, grouped.get(event.id, [])) for event in events]}


@router.get("/events/{event_id}")
def get_event(event_id: str, session: Session = Depends(get_session)) -> dict:
    event = _load_event(session, event_id)
    grouped = _deliveries_for(session, [event.id])
    return _event_body(event, grouped.get(event.id, []))


@router.post("/events/{event_id}/replay")
def replay_event(event_id: str, session: Session = Depends(get_session)) -> dict:
    event = _load_event(session, event_id)
    session.add(
        Outbox(
            event_id=event.id,
            routing_key=f"{event.provider}.{event.event_type}",
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    return {"status": "queued", "event_id": str(event.id), "correlation_id": event.correlation_id}


@router.get("/consumers")
def list_consumers(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(ConsumerControl).order_by(ConsumerControl.name)).all()
    return {"consumers": [{"name": row.name, "fail_next": row.fail_next} for row in rows]}


@router.put("/consumers/{name}")
def set_consumer(name: str, body: FailSwitch, session: Session = Depends(get_session)) -> dict:
    row = session.get(ConsumerControl, name)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown consumer")
    row.fail_next = body.fail_next
    session.commit()
    return {"name": row.name, "fail_next": row.fail_next}


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    def count(statement) -> int:
        return int(session.scalar(statement) or 0)

    queues: dict[str, int] = {}
    try:
        with celery_app.connection() as connection:
            queues = queue_depths(connection.channel())
    except Exception:
        queues = {}
    return {
        "ingested": count(select(func.count()).select_from(Intake).where(Intake.outcome == "accepted")),
        "duplicates": count(select(func.count()).select_from(Intake).where(Intake.outcome == "duplicate")),
        "delivered": count(select(func.count()).select_from(Delivery).where(Delivery.status == "succeeded")),
        "dead": count(select(func.count()).select_from(Delivery).where(Delivery.status == "dead")),
        "queues": queues,
    }
