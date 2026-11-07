"""Project execution since setup, observed by the public system report."""

import asyncio
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path

from fastapi.responses import JSONResponse


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


class SessionCoverage:
    """Public system reports: project execution since successful setup.

    Reuses the existing in-process collector/snapshot implementation. GET is
    observational; a later setup freezes the previous session before replacing
    the global disposable target. No tester secret or completed suite is needed.
    """

    def __init__(self, collector, root, store):
        self.collector, self.root, self.store = collector, root, store
        self.lock = asyncio.Lock()
        self.active = None
        self.instance_id = uuid.uuid4().hex

    def begin(self, identifier):
        self.active = {"session_id": identifier, "run_id": uuid.uuid4().hex}

    def measure(self, identifier):
        if not self.active or self.active["session_id"] != identifier:
            return None
        with tempfile.TemporaryDirectory(prefix="cra-session-measurement-") as temporary:
            path = Path(temporary) / "coverage.json"
            snapshot_report(
                self.collector,
                [self.root / "cra-service" / name for name in DOMAIN_FILES],
                path,
                self.active["run_id"],
            )
            report = json.loads(path.read_text())
        covered = sum(len(file["executed_lines"]) for file in report["files"].values())
        total = sum(file["summary"]["num_statements"] for file in report["files"].values())
        return {
            "covered": covered,
            "total": total,
            "basis": "Executable Python source statements in the six CRA domain files; project HTTP requests since this session's setup, including /api/v1 test controls. Startup, adapter setup/report and health execution excluded.",
            "provenance": {
                "session_id": identifier,
                "instance_id": self.instance_id,
                "source_sha256": {
                    "cra-service/" + name: digest(self.root / "cra-service" / name)
                    for name in DOMAIN_FILES
                },
            },
        }

    def freeze(self):
        if self.active:
            measured = self.measure(self.active["session_id"])
            with self.store.connection() as conn:
                record = self.store.get(conn, "system", self.active["session_id"])
                if record and record["status"] == "ready":
                    record["coverage_code"] = measured
                    self.store.save(conn, record)

    def install(self, app):
        app.add_middleware(SessionCoverageMiddleware, manager=self)


class SessionCoverageMiddleware:
    def __init__(self, app, manager):
        self.app, self.manager = app, manager

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            return await self.app(scope, receive, send)
        async with self.manager.lock:
            supplied = (
                dict(scope["headers"])
                .get(b"x-test-session-id", b"")
                .decode("utf-8", errors="replace")
            )
            active = self.manager.active
            if supplied and (not active or supplied != active["session_id"]):
                return await JSONResponse(
                    {
                        "message": "Session is not active on this system instance",
                        "source": "system",
                    },
                    status_code=409,
                    headers={"X-Test-Session-Conflict": "1"},
                )(scope, receive, send)
            context = active["run_id"] + "|cra-service/session" if active else "unattributed"
            self.manager.collector.switch_context(context)
            try:
                return await self.app(scope, receive, send)
            finally:
                self.manager.collector.switch_context("unattributed")
