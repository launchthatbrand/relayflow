# RelayFlow

RelayFlow accepts signed webhooks, stores a canonical event in Postgres, and publishes one message to the RabbitMQ topic exchange `relayflow.events`. Three Celery workers consume the queues bound to that exchange. Redis stores Celery task results. A failed consumer retries with exponential backoff. The last failure is rejected so RabbitMQ dead-letters it onto `relayflow.dlx`. Replay reads the Postgres row and publishes again.

## Topology

| Queue | Binding | Worker |
| --- | --- | --- |
| `crm` | `stripe.#`, `monday.#` | Celery hostname `crm@` |
| `email` | `#.completed` | Celery hostname `email@` |
| `audit` | `#` | Celery hostname `audit@` |
| `relayflow.dead` | fanout from `relayflow.dlx` | none |

The declarations live in `api/relayflow/broker/topology.py` and are passed to Celery as `task_queues`.

## Local

```bash
docker compose up -d
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd api && ../.venv/bin/alembic upgrade head && cd ..
DATABASE_URL=postgresql+psycopg://relay:relay@127.0.0.1:54329/relayflow \
CELERY_BROKER_URL=amqp://guest:guest@127.0.0.1:56729// \
CELERY_RESULT_BACKEND=redis://127.0.0.1:63799/0 \
WEBHOOK_SECRET=dev-webhook-secret \
  .venv/bin/sh api/bin/serve.sh api
```

In another shell, the same environment variables with `sh api/bin/serve.sh worker`.

The console is `web/`. For local development set `API_ORIGIN=http://127.0.0.1:8000` and run `pnpm dev`.

```bash
cd web && API_ORIGIN=http://127.0.0.1:8000 pnpm dev
```

`POST /api/webhooks/{provider}` requires `X-Relay-Signature`, the hex HMAC-SHA256 of the raw body. `POST /api/samples` signs the body with the server secret so the console can send a demo event. Providers are `stripe`, `monday`, and `email`. The JSON object needs string fields `type` and `id`.

## Tests

```bash
docker compose up -d
.venv/bin/pytest
```

## Cluster

The public console is https://relayflow.apps.onpoint.host. Postgres, Redis, and RabbitMQ stay on ClusterIP services in the `launchthat` namespace. `POSTGRES_PASSWORD`, `RABBITMQ_PASSWORD`, and `WEBHOOK_SECRET` live in the `relayflow-env` secret and are not in this repository. A push to `main` builds `ghcr.io/launchthatbrand/relayflow-api` and `ghcr.io/launchthatbrand/relayflow-web`, then rolls the API, worker, and web deployments on the k3s node.
