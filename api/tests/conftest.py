import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

os.environ["DATABASE_URL"] = "postgresql+psycopg://relay:relay@127.0.0.1:54329/relayflow"
os.environ["CELERY_BROKER_URL"] = "amqp://guest:guest@127.0.0.1:56729//"
os.environ["CELERY_RESULT_BACKEND"] = "redis://127.0.0.1:63799/0"
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["RELAY_RETRY_BASE_SECONDS"] = "0"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from relayflow.broker.topology import QUEUE_NAMES, declare_topology
from relayflow.celery_app import celery_app
from relayflow.db import SessionLocal
from relayflow.main import create_app


def _wait_port(port: int) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"127.0.0.1:{port} did not open")


@pytest.fixture(scope="session", autouse=True)
def workers():
    for port in (54329, 63799, 56729):
        _wait_port(port)
    config = Config(str(ROOT / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "api" / "alembic"))
    config.set_main_option("prepend_sys_path", str(ROOT / "api"))
    command.upgrade(config, "head")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "api")
    log_dir = ROOT / ".pytest_cache"
    log_dir.mkdir(exist_ok=True)
    processes = []
    logs = []
    for name in ("crm", "email", "audit"):
        handle = open(log_dir / f"worker-{name}.log", "w")
        logs.append(handle)
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "relayflow.celery_app",
                    "worker",
                    "-Q",
                    name,
                    "-n",
                    f"{name}@test",
                    "--pool=solo",
                    "--concurrency=1",
                    "--loglevel=info",
                ],
                cwd=ROOT / "api",
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        )
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            ping = celery_app.control.inspect(timeout=2).ping()
        except Exception:
            ping = None
        if ping and len(ping) >= 3:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("celery workers did not become ready")
    yield
    for process in processes:
        process.terminate()
    for process in processes:
        process.wait(timeout=10)
    for handle in logs:
        handle.close()


@pytest.fixture(autouse=True)
def clean_state():
    with SessionLocal() as session:
        session.execute(text("DELETE FROM deliveries"))
        session.execute(text("DELETE FROM outbox"))
        session.execute(text("DELETE FROM intakes"))
        session.execute(text("DELETE FROM events"))
        session.execute(text("UPDATE consumer_controls SET fail_next = false"))
        session.commit()
    with celery_app.connection() as connection:
        channel = connection.channel()
        declare_topology(channel)
        for name in QUEUE_NAMES:
            channel.queue_purge(name)
    yield


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def wait_until(predicate, timeout: float = 20):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.2)
    raise AssertionError(f"timed out, last value: {last}")
