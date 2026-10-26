import asyncio
import datetime
import json
import logging
import math
import os
import re
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Literal

import psycopg2
from autograder.api import install as install_autograder
from autograder.config import GRADING_DATABASE, HarnessError
from autograder.runner import shutdown_children
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from pydantic import AwareDatetime, BaseModel, Field, StrictStr, field_validator
from sbom_validation import InvalidSbom, validate_sbom
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cra.service")


@asynccontextmanager
async def lifespan(application: FastAPI):
    attempts = int(os.getenv("DB_STARTUP_ATTEMPTS", "30"))
    delay = float(os.getenv("DB_STARTUP_DELAY_SECONDS", "1"))
    timeout = float(os.getenv("DB_STARTUP_TIMEOUT_SECONDS", "180"))
    if attempts < 1 or not math.isfinite(delay) or delay < 0:
        raise ValueError("Database startup attempts must be positive and delay finite/nonnegative")
    if not math.isfinite(timeout) or timeout < 2:
        raise ValueError("Database startup timeout must be finite and at least 2 seconds")
    deadline = time.monotonic() + timeout
    for attempt in range(1, attempts + 1):
        _startup_remaining_ms(deadline)
        try:
            await run_in_threadpool(init_db, deadline=deadline)
            break
        except psycopg2.OperationalError:
            logger.warning(
                json.dumps(
                    {"event": "database_not_ready", "attempt": attempt, "attempts": attempts}
                )
            )
            if attempt == attempts:
                raise
            remaining = _startup_remaining_ms(deadline) / 1000
            await asyncio.sleep(min(delay, remaining))
    try:
        yield
    finally:
        shutdown_children()


app = FastAPI(title="CRA Vulnerability Response Service", version="1.0.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def home():
    return {
        "service": "Team 2 CRA Phase 3",
        "docs": "/docs",
        "health": "/health/ready",
        "test": "/test",
    }


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.monotonic()
    request_id = uuid.uuid4().hex
    response_status = 500
    try:
        response = await call_next(request)
        response_status = response.status_code
        response.headers["X-Request-Id"] = request_id
        return response
    finally:
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response_status,
                    "user_id": request.headers.get("X-User-Id"),
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
        )


@app.exception_handler(psycopg2.Error)
async def database_exception_handler(request: Request, exc: psycopg2.Error):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "DATABASE_ERROR", "message": "Database operation failed"}},
    )


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # If our endpoint already formatted the detail as {"error": ...}, return it directly
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    # Fallback for generic server errors
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    reasons = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "INVALID_REQUEST", "message": "; ".join(reasons)}},
    )


# --- Database Setup ---
DB_URL = os.getenv("DATABASE_URL")


def get_db_connection(
    *,
    connect_timeout: int = 5,
    statement_timeout_ms: int | None = None,
    lock_timeout_ms: int | None = None,
    read_only: bool = False,
):
    if not DB_URL:
        raise RuntimeError("DATABASE_URL must be configured")
    options = "-c timezone=UTC"
    for name, value in (
        ("statement_timeout", statement_timeout_ms),
        ("lock_timeout", lock_timeout_ms),
    ):
        if value is not None:
            if value < 1:
                raise ValueError(f"{name} must be positive")
            options += f" -c {name}={value}"
    if read_only:
        options += " -c default_transaction_read_only=on"
    return psycopg2.connect(
        DB_URL, cursor_factory=RealDictCursor, connect_timeout=connect_timeout, options=options
    )


@contextmanager
def database(**connection_options):
    """Commit on success, roll back on failure, and always close the connection."""
    conn = get_db_connection(**connection_options)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


SCHEMA_LOCK_KEY = 30861003


def _startup_remaining_ms(deadline: float) -> int:
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise TimeoutError("Database startup time budget exhausted")
    return remaining


def _startup_execute(cur, deadline, statement, parameters=None):
    # Keep SQL waits inside the remaining startup budget. These settings are
    # transaction-local and never change the database/server configuration.
    timeout = min(5000, _startup_remaining_ms(deadline))
    cur.execute("SELECT set_config('statement_timeout', %s, true)", (str(timeout),))
    cur.execute(statement, parameters)


def init_db(*, deadline: float | None = None):
    if deadline is None:
        deadline = time.monotonic() + 180
    remaining = _startup_remaining_ms(deadline)
    if remaining < 2000:
        raise TimeoutError("Insufficient startup time for a database connection")
    with (
        database(
            connect_timeout=min(5, remaining // 1000),
            statement_timeout_ms=min(5000, remaining),
            lock_timeout_ms=min(3000, remaining),
        ) as conn,
        conn.cursor() as cur,
    ):
        # Every revision uses the same transaction lock before inspecting or
        # creating schema objects. Commit/rollback releases it automatically.
        _startup_execute(cur, deadline, "SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_KEY,))
        _startup_execute(
            cur,
            deadline,
            """
        CREATE TABLE IF NOT EXISTS releases (
            release_id VARCHAR(64) PRIMARY KEY,
            product TEXT NOT NULL,
            version TEXT NOT NULL,
            support_end_date DATE NOT NULL,
            UNIQUE(product, version)
        )
        """,
        )
        _startup_execute(
            cur,
            deadline,
            """
        CREATE TABLE IF NOT EXISTS components (
            id SERIAL PRIMARY KEY,
            release_id VARCHAR(64) REFERENCES releases(release_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            purl TEXT
        )
        """,
        )
        _startup_execute(
            cur,
            deadline,
            "CREATE TABLE IF NOT EXISTS test_clock (id INT PRIMARY KEY, now TIMESTAMP WITH TIME ZONE)",
        )
        _startup_execute(
            cur,
            deadline,
            """
            SELECT table_name, column_name, data_type FROM information_schema.columns
            WHERE table_schema = current_schema() AND (
                (table_name = 'releases' AND column_name IN ('product', 'version')) OR
                (table_name = 'components' AND column_name IN ('name', 'version'))
            )
        """,
        )
        columns = cur.fetchall()
        if {(c["table_name"], c["column_name"]) for c in columns} != {
            ("releases", "product"),
            ("releases", "version"),
            ("components", "name"),
            ("components", "version"),
        }:
            raise RuntimeError("Incomplete existing schema; manual migration required")
        for column in columns:
            if column["data_type"] != "text":
                if column["data_type"] not in {"character varying", "character"}:
                    raise RuntimeError("Unexpected existing column type; manual migration required")
                # Retain the existing non-destructive VARCHAR -> TEXT upgrade,
                # without taking ALTER TABLE locks on every warm/cold start.
                _startup_execute(
                    cur,
                    deadline,
                    sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE TEXT").format(
                        sql.Identifier(column["table_name"]),
                        sql.Identifier(column["column_name"]),
                    ),
                )


@app.get("/health/live", include_in_schema=False)
def health_live():
    return JSONResponse({"status": "alive"}, headers={"Cache-Control": "no-store"})


def check_database_ready():
    with (
        database(
            connect_timeout=2, statement_timeout_ms=1000, lock_timeout_ms=500, read_only=True
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT 1")


@app.get("/health/ready", include_in_schema=False)
def health_ready():
    try:
        check_database_ready()
    except (psycopg2.Error, RuntimeError):
        # Do not return hostnames, DSNs, credentials or PostgreSQL exception text.
        return JSONResponse(
            {"status": "unavailable"}, status_code=503, headers={"Cache-Control": "no-store"}
        )
    return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})


def _current_time(cur):
    """Read the test/system UTC clock using the caller's transaction."""
    cur.execute("SELECT now FROM test_clock WHERE id = 1")
    row = cur.fetchone()
    if row and row["now"]:
        return row["now"].astimezone(datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def get_current_time():
    """Returns test clock time if set, otherwise system UTC time."""
    with database() as conn, conn.cursor() as cur:
        return _current_time(cur)


# --- Schemas ---
class ReleaseCreate(BaseModel):
    product: StrictStr
    version: StrictStr
    support_end_date: datetime.date

    @field_validator("support_end_date", mode="before")
    @classmethod
    def validate_support_end_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("support_end_date must be a YYYY-MM-DD string")
        return datetime.date.fromisoformat(value)


class ClockUpdate(BaseModel):
    now: AwareDatetime

    @field_validator("now", mode="before")
    @classmethod
    def validate_clock_string(cls, value):
        # OpenAPI date-time uses RFC 3339, not Pydantic's broader timestamp parser.
        # Calendar validity is still checked by AwareDatetime after this syntax gate.
        pattern = (
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?"
            r"(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
        )
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError("now must be an RFC 3339 date-time string with a timezone")
        return value


class ReleaseResponse(BaseModel):
    release_id: str
    product: str
    version: str
    support_end_date: datetime.date
    support_status: Literal["supported", "unsupported"]


class ComponentResponse(BaseModel):
    name: str
    version: str
    purl: str | None = None


class InventoryResponse(BaseModel):
    release_id: str
    components: list[ComponentResponse]


class SbomResponse(BaseModel):
    release_id: str
    component_count: int = Field(ge=0)


class ClockResponse(BaseModel):
    now: str = Field(json_schema_extra={"format": "date-time"})


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# --- Endpoints ---


def _release_response(row, reference_time):
    current_date = reference_time.astimezone(datetime.timezone.utc).date()
    return {
        "release_id": row["release_id"],
        "product": row["product"],
        "version": row["version"],
        "support_end_date": str(row["support_end_date"]),
        "support_status": "supported" if current_date <= row["support_end_date"] else "unsupported",
    }


@app.post(
    "/api/v1/releases",
    status_code=201,
    response_model=ReleaseResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_release(
    release: ReleaseCreate, x_user_id: str = Header(..., alias="X-User-Id", min_length=1)
):
    release_id = f"rel-{uuid.uuid4().hex[:8]}"

    try:
        with database() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO releases (release_id, product, version, support_end_date) "
                "VALUES (%s, %s, %s, %s) RETURNING release_id, product, version, support_end_date",
                (release_id, release.product, release.version, release.support_end_date),
            )
            # Capture the row and reference clock before releasing the INSERT's
            # table lock. A later reset may remove it, but cannot turn this
            # successfully committed creation into a follow-up lookup's 404.
            response = _release_response(cur.fetchone(), _current_time(cur))
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "CONFLICT", "message": "Release already exists"}},
        )

    return response


@app.get(
    "/api/v1/releases/{releaseId}",
    response_model=ReleaseResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_release(releaseId: str):
    with database() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM releases WHERE release_id = %s", (releaseId,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Release not found"}}
        )

    return _release_response(row, get_current_time())


@app.put(
    "/api/v1/releases/{releaseId}/sbom",
    response_model=SbomResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"type": "object", "description": "CycloneDX JSON document"}
                }
            },
        }
    },
)
async def upload_sbom(
    releaseId: str, request: Request, x_user_id: str = Header(..., alias="X-User-Id", min_length=1)
):
    # Verify release exists
    get_release(releaseId)

    media_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "SBOM Content-Type must be application/json",
                }
            },
        )

    try:
        sbom_data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_JSON", "message": "Malformed JSON payload"}},
        )

    try:
        components = validate_sbom(sbom_data)
    except InvalidSbom as exc:
        raise HTTPException(
            status_code=400, detail={"error": {"code": "INVALID_SBOM", "message": str(exc)}}
        ) from exc

    with database() as conn, conn.cursor() as cur:
        # Serialize replacements for this release, including empty inventories.
        cur.execute(
            "SELECT release_id FROM releases WHERE release_id = %s FOR UPDATE", (releaseId,)
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "NOT_FOUND", "message": "Release not found"}},
            )
        cur.execute("DELETE FROM components WHERE release_id = %s", (releaseId,))
        cur.executemany(
            "INSERT INTO components (release_id, name, version, purl) VALUES (%s, %s, %s, %s)",
            [(releaseId, comp["name"], comp["version"], comp.get("purl")) for comp in components],
        )

    return {"release_id": releaseId, "component_count": len(components)}


@app.get(
    "/api/v1/releases/{releaseId}/components",
    response_model=InventoryResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_components(releaseId: str):
    get_release(releaseId)  # Verify release exists

    with database() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, version, purl FROM components WHERE release_id = %s", (releaseId,)
        )
        rows = cur.fetchall()

    return {"release_id": releaseId, "components": [dict(r) for r in rows]}


# --- Test Endpoints (Section 5.3) ---


@app.post("/api/v1/test/reset", status_code=204)
def test_reset():
    with database() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE releases CASCADE")
        cur.execute("DELETE FROM test_clock")
    return None


@app.put(
    "/api/v1/test/clock", response_model=ClockResponse, responses={400: {"model": ErrorResponse}}
)
def test_clock(clock: ClockUpdate):
    reference_time = clock.now.astimezone(datetime.timezone.utc)
    with database() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO test_clock (id, now) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET now = EXCLUDED.now",
            (reference_time,),
        )
    return {"now": reference_time.isoformat().replace("+00:00", "Z")}


def service_openapi():
    """Describe actual validation errors (400) rather than FastAPI's default 422."""
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        for item in schema["paths"].values():
            for operation in item.values():
                if isinstance(operation, dict) and "responses" in operation:
                    operation["responses"].pop("422", None)
        app.openapi_schema = schema
    return app.openapi_schema


# FastAPI supports overriding its schema hook on the application instance.
app.openapi = service_openapi  # type: ignore[method-assign]


def autograder_reset(now, approved_database):
    """Opt-in adapter reset; original /api/v1 controls retain their contract."""
    if approved_database != GRADING_DATABASE:
        raise HarnessError(
            503, "RESET_DISABLED", "Adapter resets require the dedicated cra_grading database"
        )
    with database() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database() AS name")
        if cur.fetchone()["name"] != approved_database:
            raise HarnessError(
                503, "RESET_DISABLED", "Database is not the approved disposable database"
            )
        cur.execute("TRUNCATE releases CASCADE")
        cur.execute("DELETE FROM test_clock")
        if now is not None:
            cur.execute("INSERT INTO test_clock (id, now) VALUES (1, %s)", (now,))


def autograder_verify_database(approved_database):
    with database() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database() AS name")
        if approved_database != GRADING_DATABASE or cur.fetchone()["name"] != GRADING_DATABASE:
            raise HarnessError(
                503, "RESET_DISABLED", "Database is not the approved disposable database"
            )


install_autograder(
    app,
    "system",
    reset=autograder_reset,
    validate_clock=lambda value: ClockUpdate(now=value).now,
    verify_database=autograder_verify_database,
)
