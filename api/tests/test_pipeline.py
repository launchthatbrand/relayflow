from relayflow.broker.topology import audit
from relayflow.celery_app import celery_app

from test_ingest import post_webhook
from conftest import wait_until


def _event(client, event_id: str) -> dict:
    response = client.get(f"/api/events/{event_id}")
    assert response.status_code == 200
    return response.json()


def test_stripe_event_reaches_every_consumer_and_redis(client):
    created = post_webhook(
        client,
        "stripe",
        {"type": "checkout.completed", "id": "evt_stripe", "account": "acme", "amount": 2500},
    ).json()
    event_id = created["event_id"]

    def settled():
        body = _event(client, event_id)
        statuses = {name: item["status"] for name, item in body["consumers"].items()}
        return statuses if statuses == {"crm": "succeeded", "email": "succeeded", "audit": "succeeded"} else None

    assert wait_until(settled) == {"crm": "succeeded", "email": "succeeded", "audit": "succeeded"}
    result = celery_app.send_task("relayflow.deliver", args=[event_id], queue=audit)
    stored = result.get(timeout=15)
    assert stored["consumer"] == "audit"
    assert stored["status"] == "succeeded"


def test_monday_event_skips_the_email_queue(client):
    created = post_webhook(
        client,
        "monday",
        {"type": "item.updated", "id": "item_9", "account": "appropriations"},
    ).json()
    event_id = created["event_id"]

    def settled():
        body = _event(client, event_id)
        names = set(body["consumers"])
        if names == {"crm", "audit"} and all(item["status"] == "succeeded" for item in body["consumers"].values()):
            return body
        return None

    body = wait_until(settled)
    assert "email" not in body["consumers"]
    listed = client.get("/api/events").json()["events"]
    assert listed[0]["id"] == event_id
    assert listed[0]["canonical"]["type"] == "item.updated"


def test_failed_consumer_lands_in_the_dead_letter_queue(client):
    switched = client.put("/api/consumers/crm", json={"fail_next": True})
    assert switched.json()["fail_next"] is True
    created = post_webhook(
        client,
        "monday",
        {"type": "item.updated", "id": "item_dead", "account": "rules"},
    ).json()
    event_id = created["event_id"]

    def settled():
        body = _event(client, event_id)
        crm = body["consumers"].get("crm")
        audit = body["consumers"].get("audit")
        if crm and crm["status"] == "dead" and audit and audit["status"] == "succeeded":
            return body
        return None

    body = wait_until(settled, timeout=25)
    assert body["consumers"]["crm"]["attempt"] == 3
    assert [row["status"] for row in body["deliveries"] if row["consumer"] == "crm"] == ["failed", "failed", "dead"]
    stats = client.get("/api/stats").json()
    assert stats["dead"] >= 1
    assert stats["queues"]["relayflow.dead"] >= 1

    client.put("/api/consumers/crm", json={"fail_next": False})
    replayed = client.post(f"/api/events/{event_id}/replay")
    assert replayed.json()["status"] == "queued"

    def replayed_ok():
        fresh = _event(client, event_id)
        crm_rows = [row for row in fresh["deliveries"] if row["consumer"] == "crm" and row["status"] == "succeeded"]
        return fresh if crm_rows else None

    assert wait_until(replayed_ok, timeout=20)["correlation_id"] == created["correlation_id"]


def test_sample_endpoint_signs_the_payload(client):
    response = client.post(
        "/api/samples",
        json={"provider": "email", "payload": {"type": "message.completed", "id": "msg_1", "account": "desk"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    event_id = response.json()["event_id"]

    def settled():
        body = _event(client, event_id)
        if set(body["consumers"]) == {"email", "audit"}:
            return body
        return None

    assert wait_until(settled)
    direct = client.post(
        "/api/webhooks/email",
        content=b'{"type":"message.completed","id":"msg_1"}',
        headers={"x-relay-signature": "abcd"},
    )
    assert direct.status_code == 401
