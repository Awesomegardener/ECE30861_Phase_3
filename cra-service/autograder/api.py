"""Provisional ReleaseGate-compatible HTTP interface, implemented independently."""

import datetime
import uuid

import psycopg2
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import HarnessError, Settings, session_id
from .runner import Runner, empty_summary, utc_now
from .store import Store


class Harness:
    def __init__(self, settings, reset=None, validate_clock=None, verify_database=None):
        self.settings = settings
        self.store = Store(settings.database_url)
        self.runner = Runner(settings)
        self.reset = reset
        self.validate_clock = validate_clock
        self.verify_database = verify_database

    def validate(self, values):
        if set(values) - {"session_id", "target_base_url", "now"}:
            raise HarnessError(400, "INVALID_REQUEST", "Unexpected request fields")
        identifier = session_id(values["session_id"]) if "session_id" in values else None
        if "target_base_url" in values and not isinstance(values["target_base_url"], str):
            raise HarnessError(400, "INVALID_TARGET", "target_base_url must be a string")
        target = self.settings.authorize(values.get("target_base_url"))
        now = values.get("now")
        if "now" in values:
            if self.settings.role != "system" or not self.validate_clock:
                raise HarnessError(400, "INVALID_REQUEST", "now is supported only by the system")
            try:
                now = self.validate_clock(now)
            except ValueError:
                raise HarnessError(
                    400, "INVALID_REQUEST", "now must be an RFC 3339 timestamp with timezone"
                ) from None
        return identifier, target, now

    def new_session(self, conn, identifier, target, now):
        identifier = identifier or str(uuid.uuid4())
        if self.store.get(conn, self.settings.role, identifier):
            raise HarnessError(
                409, "SESSION_EXISTS", "Use a new session_id; existing reports are retained"
            )
        if self.settings.role == "system":
            if not self.reset:
                raise HarnessError(503, "NOT_CONFIGURED", "System reset adapter is unavailable")
            self.reset(now, self.settings.reset_database)
        report = dict(
            session_id=identifier,
            status="ready",
            role=self.settings.role,
            target_base_url=target,
            created_at=utc_now(),
            result=None,
            checks=[],
            summary=empty_summary(),
            error=None,
            started_at=None,
            finished_at=None,
            duration_ms=None,
            running=False,
        )
        self.store.create(conn, report)
        return report

    def setup(self, values):
        identifier, target, now = self.validate(values)
        with self.store.guard() as conn:
            report = self.new_session(conn, identifier, target, now)
        return {
            key: report[key]
            for key in ("session_id", "status", "role", "created_at", "target_base_url")
        }

    def run(self, values):
        identifier, target, now = self.validate(values)
        with self.store.guard() as conn:
            if self.verify_database:
                self.verify_database(self.settings.reset_database)
            report = self.store.get(conn, self.settings.role, identifier)
            if report is None:
                if identifier:
                    raise HarnessError(
                        404, "SESSION_NOT_FOUND", "Unknown session_id; call setup first"
                    )
                report = self.new_session(conn, None, target, now)
            else:
                if "target_base_url" in values and report["target_base_url"] != target:
                    raise HarnessError(
                        400, "INVALID_TARGET", "A session's target cannot be changed"
                    )
                # Reauthorize the stored target after configuration changes.
                self.settings.authorize(report["target_base_url"])
                if "now" in values:
                    raise HarnessError(
                        400, "INVALID_REQUEST", "Set now during setup, before running a session"
                    )
            if report["status"] == "completed":
                return self.outcome(report)
            report.update(started_at=utc_now(), running=True)
            self.store.save(conn, report)
            try:

                def heartbeat():
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")

                report.update(self.runner.execute(report["target_base_url"], heartbeat))
            except HarnessError as exc:
                report.update(result="error", summary=empty_summary(), checks=[], error=exc.message)
            except Exception as exc:
                # Never return invented passes for missing XML, timeouts or crashes.
                report.update(
                    result="error",
                    summary=empty_summary(),
                    checks=[],
                    error=f"{type(exc).__name__}: execution did not produce a complete report",
                )
            report.update(status="completed", running=False, finished_at=utc_now())
            start = datetime.datetime.fromisoformat(report["started_at"].replace("Z", "+00:00"))
            end = datetime.datetime.fromisoformat(report["finished_at"].replace("Z", "+00:00"))
            report["duration_ms"] = int((end - start).total_seconds() * 1000)
            self.store.save(conn, report)
            return self.outcome(report)

    @staticmethod
    def outcome(report):
        return dict(
            session_id=report["session_id"],
            status=report["status"],
            result=report["result"],
            summary=report["summary"],
            report_url=f"/test/report?session_id={report['session_id']}",
        )

    def report(self, identifier):
        if not self.settings.enabled or not self.settings.database_url:
            raise HarnessError(503, "NOT_CONFIGURED", "Autograder controls are not configured")
        if identifier is not None:
            identifier = session_id(identifier)
        report = self.store.read(self.settings.role, identifier)
        if report is None:
            raise HarnessError(404, "SESSION_NOT_FOUND", "Unknown session_id or no session yet")
        return report


async def request_values(request):
    values = dict(request.query_params)
    if any(len(request.query_params.getlist(key)) != 1 for key in values):
        raise HarnessError(400, "INVALID_REQUEST", "Duplicate query parameters")
    body = await request.body()
    if len(body) > 8192:
        raise HarnessError(400, "INVALID_REQUEST", "Request body exceeds 8192 bytes")
    if body:
        try:
            data = await request.json()
        except ValueError:
            raise HarnessError(400, "INVALID_REQUEST", "Malformed JSON body") from None
        if not isinstance(data, dict):
            raise HarnessError(400, "INVALID_REQUEST", "Body must be a JSON object")
        for key, value in data.items():
            if key in values and values[key] != value:
                raise HarnessError(400, "INVALID_REQUEST", "Conflicting body and query values")
            values[key] = value
    return values


def install(
    application, role, *, reset=None, validate_clock=None, verify_database=None, settings=None
):
    harness = Harness(
        settings or Settings.environment(role), reset, validate_clock, verify_database
    )
    application.state.autograder = harness
    router = APIRouter(tags=["Provisional autograder adapter"])

    async def call(operation, *arguments):
        try:
            result = await run_in_threadpool(operation, *arguments)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except HarnessError as exc:
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
            )
        except psycopg2.Error:
            return JSONResponse(
                {
                    "error": {
                        "code": "STORE_UNAVAILABLE",
                        "message": "Report storage unavailable; retry later",
                    }
                },
                status_code=503,
            )

    @router.get("/test")
    def describe():
        reset_ready = False
        if role == "system" and harness.verify_database:
            try:
                harness.settings.authorize()
                harness.verify_database(harness.settings.reset_database)
                reset_ready = True
            except (HarnessError, psycopg2.Error, RuntimeError):
                pass
        return dict(
            service="Team 2 CRA Phase 3",
            role=role,
            description="Independent pytest adapter; provisional Team 6 interface compatibility. Runs reset disposable targets.",
            enabled=harness.settings.enabled,
            reset_ready=reset_ready,
            endpoints={
                "setup": "POST /test/setup",
                "run": "POST /test/run",
                "report": "GET /test/report?session_id=...",
            },
        )

    @router.post("/test/setup")
    async def setup(request: Request):
        try:
            values = await request_values(request)
        except HarnessError as exc:
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
            )
        return await call(harness.setup, values)

    @router.post("/test/run")
    async def run(request: Request):
        try:
            values = await request_values(request)
        except HarnessError as exc:
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
            )
        return await call(harness.run, values)

    @router.get("/test/report")
    async def report(request: Request):
        return await call(harness.report, request.query_params.get("session_id"))

    application.include_router(router)
    return harness
