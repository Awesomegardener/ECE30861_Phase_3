"""Request-driven, authenticated coverage windows for a single grading replica.

The collector starts before application/worker imports. Reports are exported
before /test/run returns, with no shutdown hook, mounted volume or background job.
"""

import asyncio
import base64
import datetime
import gzip
import hashlib
import hmac
import json
import logging
import re
import secrets
import tempfile
import time
import traceback
import uuid
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import HarnessError, session_id
from .measured_coverage import digest, measured_coverage
from .runner import EXPECTED_TESTS

DOMAIN_FILES = (
    "main.py",
    "sbom_validation.py",
    "timestamps.py",
    "phase4.py",
    "purl_matching.py",
    "osv_source.py",
)


def snapshot_report(collector, files, path, run_id):
    import coverage

    # An active collector's get_data() can reset query filters during reporting.
    # Copy under the request lock; report from an independent, stopped dataset.
    snapshot = coverage.Coverage(data_file=None, branch=True, config_file=False)
    snapshot.get_data().update(collector.get_data())
    pattern = re.escape(run_id) + r"\|cra-service/"
    snapshot.json_report(
        morfs=[str(p) for p in files],
        outfile=str(path),
        contexts=[pattern],
        show_contexts=False,
    )
    # Coverage 7's region sections repeat a full file's contexts for each
    # function/class. Export file metrics, then add filtered physical contexts
    # once per file using the public Data API, avoiding hundreds of MB per run.
    report = json.loads(path.read_text())
    data = snapshot.get_data()
    data.set_query_contexts([pattern])
    actual_files = {p.name: str(p.resolve()) for p in files}
    for name, item in report["files"].items():
        item.pop("functions", None)
        item.pop("classes", None)
        item["contexts"] = data.contexts_by_lineno(actual_files[Path(name).name])
    report["meta"].update(
        show_contexts=True,
        projection="file-level metrics and physical contexts; redundant region sections omitted",
    )
    path.write_text(json.dumps(report))


class LiveCoverage:
    def __init__(
        self,
        collector,
        root,
        settings,
        verify_database,
        *,
        monotonic=time.monotonic,
        session_running=None,
    ):
        if not settings.coverage_enabled or len(settings.coverage_token) < 32:
            raise ValueError(
                "Grading coverage requires enabled controls and a secret of at least 32 characters"
            )
        self.collector, self.root, self.settings = collector, root, settings
        self.verify_database = verify_database
        self.monotonic = monotonic
        self.session_running = session_running
        self.lock = asyncio.Lock()
        self.active = None
        self.instance_id = uuid.uuid4().hex

    def current(self):
        if self.active and self.monotonic() >= self.active["deadline"]:
            self.active = None
        return self.active

    def authorize(self, request):
        supplied = request.headers.get("X-CRA-Coverage-Key", "")
        if not hmac.compare_digest(supplied.encode(), self.settings.coverage_token.encode()):
            raise HarnessError(
                403, "COVERAGE_FORBIDDEN", "Coverage control requires service authentication"
            )

    async def start(self, payload):
        async with self.lock:
            if set(payload) != {"role", "session_id", "timeout"}:
                raise HarnessError(400, "INVALID_REQUEST", "Invalid coverage start fields")
            role = payload["role"]
            identifier = session_id(payload["session_id"])
            timeout = payload["timeout"]
            if (
                not isinstance(role, str)
                or role not in {"system", "tester"}
                or type(timeout) is not int
                or not 1 <= timeout <= 1800
            ):
                raise HarnessError(400, "INVALID_REQUEST", "Invalid coverage role or timeout")
            self.settings.authorize()
            self.verify_database(self.settings.reset_database)
            active = self.current()
            if self.session_running:
                if not self.session_running(role, identifier):
                    raise HarnessError(
                        409, "COVERAGE_SESSION_MISMATCH", "Report session is not running"
                    )
                if active and not self.session_running(active["role"], active["session_id"]):
                    # The shared execution lock recovered an abandoned parent.
                    self.active, active = None, None
            if active and (active["role"], active["session_id"]) != (role, identifier):
                raise HarnessError(409, "COVERAGE_BUSY", "Another measurement is active")
            if not active:
                active = {
                    "role": role,
                    "session_id": identifier,
                    "run_id": "coverage-" + role + "-" + uuid.uuid4().hex,
                    "request_token": secrets.token_urlsafe(32),
                    "deadline": self.monotonic() + timeout + 30,
                    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                self.active = active
            return {
                **{key: active[key] for key in ("run_id", "request_token")},
                "instance_id": self.instance_id,
            }

    async def end(self, payload, *, abort=False):
        async with self.lock:
            active = self.current()
            if not active or payload.get("run_id") != active["run_id"]:
                raise HarnessError(
                    409,
                    "COVERAGE_SESSION_MISMATCH",
                    "Measurement session is not active on this instance",
                )
            expected = {"run_id"} if abort else {"run_id", "report"}
            if set(payload) != expected:
                raise HarnessError(400, "INVALID_REQUEST", "Invalid coverage completion fields")
            if abort:
                self.active = None
                return {"aborted": True}
            report = payload["report"]
            if not isinstance(report, dict) or (report.get("role"), report.get("session_id")) != (
                active["role"],
                active["session_id"],
            ):
                raise HarnessError(
                    409, "COVERAGE_SESSION_MISMATCH", "Report identity does not match measurement"
                )
            checks = report.get("checks")
            if not isinstance(checks, list) or len(checks) != EXPECTED_TESTS:
                raise HarnessError(
                    400, "INVALID_REQUEST", "Complete suite outcomes are required for coverage"
                )
            if not all(
                isinstance(c, dict)
                and isinstance(c.get("id"), str)
                and isinstance(c.get("title"), str)
                and type(c.get("passed")) is bool
                for c in checks
            ):
                raise HarnessError(400, "INVALID_REQUEST", "Invalid coverage check records")
            self.collector.switch_context("unattributed")
            with tempfile.TemporaryDirectory(prefix="cra-measurement-") as temporary:
                directory = Path(temporary)
                path = directory / "server-coverage.json"
                snapshot_report(
                    self.collector,
                    [self.root / "cra-service" / name for name in DOMAIN_FILES],
                    path,
                    active["run_id"],
                )
                import coverage

                metadata = {
                    **{key: active[key] for key in ("run_id", "role", "session_id", "started_at")},
                    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "coverage_version": coverage.__version__,
                    "instance_id": self.instance_id,
                    "source_sha256": {
                        "cra-service/" + name: digest(self.root / "cra-service" / name)
                        for name in DOMAIN_FILES
                    },
                    "test_sha256": {
                        "cra-service/" + name: digest(self.root / "cra-service" / name)
                        for name in ("test_api.py", "test_phase4_api.py")
                    },
                    "collector_sha256": {
                        name: digest(self.root / "cra-service/autograder" / name)
                        for name in ("live_coverage.py", "grading_server.py", "pytest_guard.py")
                    },
                }
                (directory / "metadata.json").write_text(json.dumps(metadata))
                result = measured_coverage(self.root, directory, report)
                if result["code"]["provenance"]["attributed_tests"] != EXPECTED_TESTS:
                    raise HarnessError(
                        503,
                        "COVERAGE_UNAVAILABLE",
                        "Incomplete server attribution; check single-replica routing",
                    )
                raw = path.read_bytes()
                result["code"]["trace_artifact"] = {
                    "encoding": "gzip+base64",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "data": base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii"),
                }
            self.active = None
            return result

    def install(self, app):
        app.add_middleware(LiveCoverageMiddleware, manager=self)

        async def control(request, operation):
            try:
                self.authorize(request)
                raw = await request.body()
                if len(raw) > 2 * 1024 * 1024:
                    raise HarnessError(400, "INVALID_REQUEST", "Coverage body is too large")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("object required")
                result = await (
                    self.start(payload)
                    if operation == "start"
                    else self.end(payload, abort=operation == "abort")
                )
                return JSONResponse(result, headers={"Cache-Control": "no-store"})
            except HarnessError as exc:
                return JSONResponse(
                    {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
                )
            except Exception as exc:
                frame = traceback.extract_tb(exc.__traceback__)[-1]
                logging.getLogger(__name__).warning(
                    "coverage_capture_failed type=%s source=%s line=%s",
                    type(exc).__name__,
                    Path(frame.filename).name,
                    frame.lineno,
                )
                return JSONResponse(
                    {
                        "error": {
                            "code": "COVERAGE_UNAVAILABLE",
                            "message": "Server measurement unavailable",
                        }
                    },
                    status_code=503,
                )

        @app.post("/internal/coverage/start", include_in_schema=False)
        async def start(request: Request):
            return await control(request, "start")

        @app.post("/internal/coverage/finish", include_in_schema=False)
        async def finish(request: Request):
            return await control(request, "finish")

        @app.post("/internal/coverage/abort", include_in_schema=False)
        async def abort(request: Request):
            return await control(request, "abort")


class LiveCoverageMiddleware:
    def __init__(self, app, manager):
        self.app, self.manager = app, manager

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["path"] == "/test/run"
            or scope["path"].startswith("/internal/coverage/")
        ):
            return await self.app(scope, receive, send)
        async with self.manager.lock:
            headers = dict(scope["headers"])
            run_id = headers.get(b"x-cra-coverage-run", b"").decode("ascii", errors="replace")
            token = headers.get(b"x-cra-coverage-request", b"").decode("ascii", errors="replace")
            test = headers.get(b"x-cra-coverage-test", b"").decode("ascii", errors="replace")
            active = self.manager.current()
            context = "unattributed"
            if run_id or token:
                if (
                    not active
                    or run_id != active["run_id"]
                    or not hmac.compare_digest(token.encode(), active["request_token"].encode())
                    or not re.fullmatch(
                        r"cra-service/test_(api|phase4_api)\.py::test_[^\r\n]{1,1000}", test
                    )
                ):
                    return await JSONResponse(
                        {
                            "error": {
                                "code": "COVERAGE_SESSION_MISMATCH",
                                "message": "Coverage request is not valid on this instance",
                            }
                        },
                        status_code=409,
                    )(scope, receive, send)
                context = run_id + "|" + test
            self.manager.collector.switch_context(context)
            try:
                return await self.app(scope, receive, send)
            finally:
                self.manager.collector.switch_context("unattributed")
