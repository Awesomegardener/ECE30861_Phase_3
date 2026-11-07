"""Cross-team Testing Interface v0.4.2: prose requirements are authoritative."""

import json
import logging
import re
import time
import uuid

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .client import TargetClient
from .config import HarnessError, Settings, normalize_target, session_id
from .coverage import unavailable_coverage
from .runner import Runner
from .store import Store


def error_response(exc, role):
    return JSONResponse(
        {"message": exc.message, "source": exc.source or role},
        status_code=exc.status,
        headers={"Cache-Control": "no-store"},
    )


def fields(values, required, optional=()):
    if not isinstance(values, dict) or not set(required) <= values.keys():
        raise HarnessError(
            400, "INVALID_REQUEST", "Missing required fields: " + ", ".join(required)
        )
    extra = set(values) - set(required) - set(optional)
    if extra:
        # Names only, bounded and sanitized: never log payload values or nested data.
        safe = [
            name if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,47}", name) else "<redacted-field>"
            for name in sorted(extra)[:12]
        ]
        logging.getLogger(__name__).warning(
            "Rejected cross-team request fields: %s", ", ".join(safe)
        )
        raise HarnessError(400, "INVALID_REQUEST", "Unexpected request fields: " + ", ".join(safe))


class Harness:
    def __init__(self, settings, reset=None, validate_clock=None, verify_database=None):
        self.settings = settings
        self.store = Store(settings.database_url)
        self.runner = Runner(settings)
        self.reset, self.validate_clock, self.verify_database = (
            reset,
            validate_clock,
            verify_database,
        )

    def setup(self, values):
        if self.settings.role == "tester":
            fields(values, ("target_url",), ("setup",))
            target = self.settings.authorize(normalize_target(values["target_url"]))
            starting = values.get("setup", {})
            if not isinstance(starting, dict):
                raise HarnessError(400, "INVALID_REQUEST", "setup must be an object")
            identifier = str(uuid.uuid4())
            record = dict(
                session_id=identifier,
                role="tester",
                status="preparing",
                target_url=target,
                interface_version="0.4.2",
            )
            with self.store.guard() as conn:
                if self.store.pending_tester(conn):
                    raise HarnessError(409, "SESSION_CONFLICT", "Another tester session is pending")
                self.store.create(conn, record)
            # Never hold the shared execution mutex across a system setup RPC.
            try:
                TargetClient(self.settings, target).setup(identifier, starting)
            except Exception:
                try:
                    with self.store.connection() as conn:
                        self.store.delete_preparing(conn, "tester", identifier)
                except Exception:
                    # The reservation is not runnable even if cleanup is unavailable.
                    pass
                raise
            with self.store.guard() as conn:
                record["status"] = "ready"
                self.store.save(conn, record)
            return {"session_id": identifier}

        fields(values, ("session_id", "setup"))
        identifier = session_id(values["session_id"])
        starting = values["setup"]
        if not isinstance(starting, dict) or set(starting) - {"now"}:
            raise HarnessError(
                400, "INVALID_REQUEST", "System setup supports {} or an optional now clock"
            )
        now = None
        if "now" in starting:
            try:
                if not self.validate_clock:
                    raise ValueError()
                now = self.validate_clock(starting["now"])
            except (ValueError, TypeError):
                raise HarnessError(
                    400, "INVALID_REQUEST", "now must be a timezone-aware RFC 3339 timestamp"
                ) from None
        self.settings.authorize()
        record = dict(
            session_id=identifier,
            role="system",
            status="preparing",
            interface_version="0.4.2",
            coverage_code=unavailable_coverage()["code"],
        )
        with self.store.guard() as conn:
            if self.store.get(conn, "system", identifier):
                raise HarnessError(409, "SESSION_EXISTS", "Session ID already exists")
            if self.store.pending_tester(conn, except_id=identifier):
                raise HarnessError(
                    409, "SESSION_CONFLICT", "A tester session owns the target window"
                )
            self.store.create(conn, record)
            try:
                if not self.reset:
                    raise RuntimeError("System preparation is unavailable")
                self.reset(now, self.settings.reset_database)
            except Exception:
                record["status"] = "failed"
                self.store.save(conn, record)
                raise HarnessError(
                    500,
                    "PREPARATION_FAILED",
                    "Could not initialize the session database.",
                    "system",
                ) from None
            record["status"] = "ready"
            self.store.save(conn, record)
        return {"session_id": identifier}

    def run(self, values):
        fields(values, ("session_id",))
        identifier = session_id(values["session_id"])
        if not self.settings.enabled:
            raise HarnessError(500, "NOT_CONFIGURED", "Tester controls are disabled")
        deadline = time.monotonic() + self.settings.timeout
        with self.store.guard() as conn:
            record = self.store.get(conn, "tester", identifier)
            if not record:
                raise HarnessError(404, "SESSION_NOT_FOUND", "Unknown session_id")
            if record.get("interface_version") != "0.4.2":
                raise HarnessError(
                    409, "LEGACY_SESSION", "Session predates this interface; create a new session"
                )
            if record["status"] != "ready":
                raise HarnessError(
                    409, "SESSION_CONFLICT", "One run is allowed per prepared session"
                )
            self.settings.authorize(record["target_url"])
            record.update(status="running", running=True)
            self.store.save(conn, record)

            def heartbeat():
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")

            try:
                body, aborted = self.runner.execute_suite(
                    record["target_url"], identifier, deadline, heartbeat
                )
            except Exception:
                body = self.runner.aborted_report(
                    record["target_url"], identifier, "Tester could not execute its suite"
                )
                aborted = True
            record.update(status="aborted" if aborted else "completed", running=False, body=body)
            self.store.save(conn, record)
            if aborted:
                raise HarnessError(500, "TESTER_ABORTED", body["message"], "tester")
            return body

    def report(self, identifier):
        identifier = session_id(identifier)
        if not self.settings.enabled or not self.settings.database_url:
            raise HarnessError(500, "NOT_CONFIGURED", "Report storage is not configured")
        record = self.store.read(self.settings.role, identifier)
        if record is None:
            raise HarnessError(404, "SESSION_NOT_FOUND", "Unknown session_id")
        if self.settings.role == "tester":
            if record.get("interface_version") != "0.4.2":
                raise HarnessError(
                    409,
                    "LEGACY_SESSION",
                    "Session predates this report format; create a new session",
                )
            if record["status"] not in {"completed", "aborted"}:
                raise HarnessError(409, "REPORT_NOT_READY", "The suite has not ended")
            return record["body"]
        if record["status"] == "preparing":
            raise HarnessError(409, "REPORT_NOT_READY", "System preparation is in progress")
        if record["status"] != "ready":
            raise HarnessError(500, "PREPARATION_FAILED", "System preparation failed", "system")
        return {
            "session_id": identifier,
            "coverage": {
                "code": record.get(
                    "coverage_code",
                    unavailable_coverage("Session predates source coverage collection")["code"],
                )
            },
        }


async def request_values(request):
    if request.query_params:
        raise HarnessError(400, "INVALID_REQUEST", "Use the required JSON request body")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HarnessError(400, "INVALID_REQUEST", "Content-Type application/json is required")
    raw = await request.body()
    if not raw or len(raw) > 8192:
        raise HarnessError(
            400, "INVALID_REQUEST", "A JSON object of at most 8192 bytes is required"
        )

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    try:

        def invalid_constant(value):
            raise ValueError("Non-JSON numeric constant")

        data = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise HarnessError(
            400, "INVALID_REQUEST", "Malformed JSON or duplicate object fields"
        ) from None
    if not isinstance(data, dict):
        raise HarnessError(400, "INVALID_REQUEST", "Body must be a JSON object")
    return data


def install(
    application, role, *, reset=None, validate_clock=None, verify_database=None, settings=None
):
    harness = Harness(
        settings or Settings.environment(role), reset, validate_clock, verify_database
    )
    application.state.autograder = harness
    router = APIRouter(tags=["Cross-team testing"])

    async def call(operation, *arguments, status_code=200):
        try:
            result = await run_in_threadpool(operation, *arguments)
            return JSONResponse(
                result, status_code=status_code, headers={"Cache-Control": "no-store"}
            )
        except HarnessError as exc:
            return error_response(exc, role)
        except Exception:
            return error_response(
                HarnessError(500, "SERVICE_FAILURE", "Test service operation failed"), role
            )

    @router.get("/test")
    def describe():
        return dict(
            service="Team 2 CRA",
            role=role,
            enabled=harness.settings.enabled,
            endpoints={
                "setup": "POST /test/setup",
                "report": "GET /test/report?session_id=...",
                **({"run": "POST /test/run"} if role == "tester" else {}),
            },
        )

    @router.post("/test/setup", status_code=201)
    async def setup(request: Request):
        try:
            values = await request_values(request)
        except HarnessError as exc:
            return error_response(exc, role)
        manager = getattr(application.state, "session_coverage", None)
        if role == "system" and manager:
            async with manager.lock:
                try:
                    await run_in_threadpool(manager.freeze)
                except Exception:
                    return error_response(
                        HarnessError(
                            500, "COVERAGE_FAILURE", "System measurement could not be retained"
                        ),
                        role,
                    )
                response = await call(harness.setup, values, status_code=201)
                if response.status_code == 201:
                    manager.begin(values["session_id"])
                return response
        return await call(harness.setup, values, status_code=201)

    if role == "tester":

        @router.post("/test/run")
        async def run(request: Request):
            try:
                values = await request_values(request)
            except HarnessError as exc:
                return error_response(exc, role)
            return await call(harness.run, values)

    @router.get("/test/report")
    async def report(request: Request):
        if (
            await request.body()
            or set(request.query_params) != {"session_id"}
            or len(request.query_params.getlist("session_id")) != 1
        ):
            return error_response(
                HarnessError(400, "INVALID_REQUEST", "One session_id query parameter is required"),
                role,
            )
        response = await call(harness.report, request.query_params["session_id"])
        manager = getattr(application.state, "session_coverage", None)
        if role == "system" and manager and response.status_code == 200:
            async with manager.lock:
                # Setup may have frozen/replaced this context while we waited.
                response = await call(harness.report, request.query_params["session_id"])
                if response.status_code != 200:
                    return response
                try:
                    code = await run_in_threadpool(
                        manager.measure, request.query_params["session_id"]
                    )
                    if code is not None:
                        return JSONResponse(
                            {
                                "session_id": request.query_params["session_id"],
                                "coverage": {"code": code},
                            },
                            headers={"Cache-Control": "no-store"},
                        )
                except Exception:
                    return JSONResponse(
                        {
                            "session_id": request.query_params["session_id"],
                            "coverage": {
                                "code": unavailable_coverage(
                                    "Source measurement failed on this system instance"
                                )["code"]
                            },
                        }
                    )
        return response

    application.include_router(router)
    original_openapi = application.openapi

    def contract_openapi():
        schema = original_openapi()
        name = "autograder-openapi.yaml" if role == "tester" else "system-test-openapi.yaml"
        contract = yaml.safe_load((harness.settings.root / "docs" / name).read_text())
        schema["openapi"] = contract["openapi"]
        schema["paths"].update(contract["paths"])
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            contract["components"]["schemas"]
        )
        return schema

    application.openapi = contract_openapi
    return harness
