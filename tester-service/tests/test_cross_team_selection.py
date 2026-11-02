"""Offline endpoint/argv checks; never execute pytest against either public URL."""

import asyncio
import copy
import json
from contextlib import contextmanager

import pytest
from autograder.api import install
from autograder.config import TEAM2, TEAM6, Settings
from autograder.runner import EXPECTED_TESTS, SUITE_FILES
from fastapi import FastAPI
from starlette.requests import Request


class MemoryStore:
    """Only test session wiring; real PostgreSQL persistence is checked separately."""

    def __init__(self):
        self.rows = {}

    @contextmanager
    def guard(self):
        yield None

    def get(self, conn, role, identifier):
        return copy.deepcopy(self.rows.get((role, identifier)))

    def create(self, conn, report):
        self.save(conn, report)

    def save(self, conn, report):
        self.rows[(report["role"], report["session_id"])] = copy.deepcopy(report)

    def read(self, role, identifier):
        return self.get(None, role, identifier)


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("AUTOGRADER_ENABLED", "true")
    monkeypatch.setenv("AUTOGRADER_ALLOW_RESET", "true")
    monkeypatch.setenv("AUTOGRADER_DATABASE_URL", "unused-offline-test-dsn")
    monkeypatch.setenv("AUTOGRADER_DEFAULT_TARGET", TEAM2)
    monkeypatch.setenv("AUTOGRADER_APPROVED_TARGETS", f"{TEAM2},{TEAM6}")
    app = FastAPI()
    harness = install(app, "tester", settings=Settings.environment("tester"))
    harness.store = MemoryStore()
    launches = []
    monkeypatch.setattr("autograder.runner.verify_public_target", lambda _: None)

    def stop_before_execution(command, **kwargs):
        launches.append((command, kwargs["env"]))
        raise RuntimeError("Offline verification stops before child/network execution")

    monkeypatch.setattr("autograder.runner.subprocess.Popen", stop_before_execution)

    def request(method, path, payload=None, query=""):
        async def receive():
            return {"type": "http.request", "body": json.dumps(payload or {}).encode()}

        req = Request(
            {
                "type": "http",
                "method": method,
                "path": path,
                "query_string": query.encode(),
                "headers": [],
            },
            receive,
        )
        route = next(r for r in app.routes if r.path == path and method in r.methods)
        response = asyncio.run(route.endpoint(req))
        return response.status_code, json.loads(response.body)

    return harness, request, launches


@pytest.mark.parametrize("target", [TEAM2, TEAM6])
def test_setup_run_and_report_keep_explicit_target_and_complete_suite_argv(adapter, target):
    harness, request, launches = adapter
    assert harness.settings.approved_targets == {TEAM2, TEAM6}
    status, setup = request("POST", "/test/setup", {"target_base_url": target})
    assert status == 200 and setup["target_base_url"] == target
    identifier = setup["session_id"]
    assert launches == []  # Tester setup does not contact/reset the selected system.
    status, outcome = request("POST", "/test/run", {"session_id": identifier})
    assert status == 200 and outcome["result"] == "error"
    assert len(launches) == 1
    command, environment = launches[0]
    assert all(file in command for file in SUITE_FILES)
    assert EXPECTED_TESTS == 353
    assert command[command.index("--base-url") + 1] == target
    assert environment["CRA_HARNESS_TARGET"] == target
    assert "autograder.pytest_guard" in command
    status, report = request("GET", "/test/report", query=f"session_id={identifier}")
    assert status == 200 and report["target_base_url"] == target
    assert report["result"] == "error" and report["checks"] == []
    assert report["summary"]["passed"] == report["summary"]["total"] == 0
    assert "RuntimeError" in report["error"]  # Interrupted execution never fabricates passes.


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com",
        "http://169.254.169.254",
        "http://136.116.160.182:8081",
        "https://136.116.160.182:8080",
        TEAM2 + ".evil.example",
        TEAM6 + "@evil.example",
    ],
)
def test_unapproved_cross_team_target_is_rejected_before_session_or_execution(adapter, target):
    harness, request, launches = adapter
    status, body = request("POST", "/test/setup", {"target_base_url": target})
    assert status == 400 and body["error"]["code"] == "INVALID_TARGET"
    assert harness.store.rows == {} and launches == []


def test_selected_target_cannot_be_switched_or_used_after_approval_removed(adapter):
    harness, request, launches = adapter
    _, setup = request("POST", "/test/setup", {"target_base_url": TEAM6})
    payload = {"session_id": setup["session_id"]}
    status, body = request("POST", "/test/run", {**payload, "target_base_url": TEAM2})
    assert status == 400 and body["error"]["code"] == "INVALID_TARGET"
    harness.settings.approved_targets = frozenset({TEAM2})
    status, body = request("POST", "/test/run", payload)
    assert status == 400 and body["error"]["code"] == "INVALID_TARGET"
    assert launches == []
