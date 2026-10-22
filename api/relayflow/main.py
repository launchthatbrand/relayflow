import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from relayflow.celery_app import open_topology
from relayflow.logging import configure_logging
from relayflow.publisher import publish_pending
from relayflow.routes import router

logger = logging.getLogger(__name__)


def publish_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            publish_pending()
        except Exception:
            logger.exception("outbox publish failed")
        stop.wait(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    open_topology()
    stop = threading.Event()
    thread = threading.Thread(target=publish_loop, args=(stop,), name="outbox", daemon=True)
    thread.start()
    yield
    stop.set()
    thread.join(timeout=2)


def create_app() -> FastAPI:
    app = FastAPI(title="RelayFlow", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
