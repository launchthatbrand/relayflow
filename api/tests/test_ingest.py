import json

from relayflow.signatures import sign

SECRET = "test-secret"


def post_webhook(client, provider: str, payload: dict):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(
        f"/api/webhooks/{provider}",
        content=raw,
        headers={"content-type": "application/json", "x-relay-signature": sign(SECRET, raw)},
    )


def test_rejects_a_bad_signature(client):
    response = client.post(
        "/api/webhooks/stripe",
        content=b'{"type":"checkout.completed","id":"evt_1"}',
        headers={"x-relay-signature": "nope"},
    )
    assert response.status_code == 401


def test_rejects_a_payload_without_type(client):
    raw = b'{"id":"evt_1"}'
    response = client.post(
        "/api/webhooks/stripe",
        content=raw,
        headers={"x-relay-signature": sign(SECRET, raw)},
    )
    assert response.status_code == 422


def test_duplicate_webhook_does_not_publish_again(client):
    payload = {"type": "checkout.completed", "id": "evt_dup", "account": "acme"}
    first = post_webhook(client, "stripe", payload)
    second = post_webhook(client, "stripe", payload)
    assert first.status_code == 200
    assert first.json()["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["event_id"] == first.json()["event_id"]
    stats = client.get("/api/stats").json()
    assert stats["ingested"] == 1
    assert stats["duplicates"] == 1
