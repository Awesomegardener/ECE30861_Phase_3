"""Separate Team 2 HTTP tester. Shares our adapter, never the peer implementation."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cra-service"))

from autograder.api import install  # noqa: E402
from autograder.runner import shutdown_children  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402


@asynccontextmanager
async def lifespan(application):
    yield
    shutdown_children()


app = FastAPI(title="Team 2 CRA HTTP tester", version="1.0.0", lifespan=lifespan)
harness = install(app, "tester")


@app.get("/")
def home():
    return {"service": "Team 2 CRA HTTP tester", "docs": "/docs", "test": "/test"}


@app.get("/health/live", include_in_schema=False)
def live():
    return {"status": "alive"}


@app.get("/health/ready", include_in_schema=False)
def ready():
    try:
        harness.settings.authorize()
        with harness.store.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return JSONResponse({"status": "ready"})
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
