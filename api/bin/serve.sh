#!/bin/sh
set -eu
cd /app/api
python - <<'PY'
import time

from sqlalchemy import create_engine, text

from relayflow.config import settings

for _ in range(30):
    try:
        with create_engine(settings.database_url).connect() as connection:
            connection.execute(text("select 1"))
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("database not ready")
PY
alembic upgrade head
if [ "${1:-api}" = "worker" ]; then
  python -m relayflow.declare
  celery -A relayflow.celery_app worker -Q crm -n crm@%h --pool=solo --concurrency=1 --loglevel=info &
  celery -A relayflow.celery_app worker -Q email -n email@%h --pool=solo --concurrency=1 --loglevel=info &
  celery -A relayflow.celery_app worker -Q audit -n audit@%h --pool=solo --concurrency=1 --loglevel=info &
  wait
else
  exec uvicorn relayflow.main:app --host 0.0.0.0 --port 8000
fi
