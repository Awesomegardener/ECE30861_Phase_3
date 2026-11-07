"""Contract cases derived from the full Cross-team Testing Interface prose.

Real ASGI routes with in-memory storage/RPC transport; no public network/SQL.
"""

import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from autograder.api import install
from autograder.client import TargetClient
from autograder.config import TEAM2, HarnessError, Settings
from autograder.reporting import report_body
from fastapi import FastAPI


def call(app, method, path, payload=None, *, query=None, raw=None):
    messages = []

    async def receive():
        return {
            "type": "http.request",
            "body": raw
            if raw is not None
            else json.dumps(payload).encode()
            if payload is not None
            else b"",
            "more_body": False,
        }

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": urlencode(query or {}).encode(),
        "headers": [(b"content-type", b"application/json")],
        "server": ("isolated.invalid", 80),
        "client": ("127.0.0.1", 1),
    }
    asyncio.run(app(scope, receive, send))
    return (
        next(m["status"] for m in messages if m["type"] == "http.response.start"),
        json.loads(
            b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        ),
    )


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.lock = threading.Lock()

    @contextmanager
    def connection(self):
        yield None

    @contextmanager
    def guard(self):
        if not self.lock.acquire(blocking=False):
            raise HarnessError(409, "BUSY", "Another operation is in progress")
        try:
            yield None
        finally:
            self.lock.release()

    def get(self, conn, role, identifier=None):
        return copy.deepcopy(self.rows.get((role, identifier)))

    def read(self, role, identifier):
        return self.get(None, role, identifier)

    def create(self, conn, record):
        if (record["role"], record["session_id"]) in self.rows:
            raise HarnessError(409, "EXISTS", "Session exists")
        self.save(conn, record)

    def save(self, conn, record):
        self.rows[(record["role"], record["session_id"])] = copy.deepcopy(record)

    def delete_preparing(self, conn, role, identifier):
        self.rows.pop((role, identifier), None)

    def pending_tester(self, conn, *, except_id=None):
        return any(
            role == "tester"
            and row.get("interface_version") == "0.4.2"
            and identifier != except_id
            and row["status"] in {"preparing", "ready", "running"}
            for (role, identifier), row in self.rows.items()
        )


@pytest.fixture
def pair(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    base = Settings("tester", True, True, "unused", TEAM2, frozenset({TEAM2}), "cra_grading", 10)
    tester, system = FastAPI(), FastAPI()
    resets = []
    th = install(tester, "tester", settings=base)
    sh = install(
        system,
        "system",
        settings=replace(
            base,
            role="system",
            default_target="http://127.0.0.1:8080",
            approved_targets=frozenset({"http://127.0.0.1:8080"}),
        ),
        reset=lambda now, db: resets.append((now, db)),
        validate_clock=lambda value: value,
    )
    store = MemoryStore()
    th.store = sh.store = store
    forwarded = []

    def rpc(self, method, path, **kwargs):
        forwarded.append((method, path, copy.deepcopy(kwargs)))
        status, body = call(system, method, path, kwargs.get("json"), query=kwargs.get("params"))
        return SimpleNamespace(status_code=status, json=lambda: body)

    monkeypatch.setattr(TargetClient, "request", rpc)
    executions = []

    def execute(target, identifier, deadline, heartbeat):
        executions.append(identifier)
        body = report_body(
            target,
            identifier,
            [{"test_id": "T-1", "outcome": "pass", "message": "Expected error received."}],
        )
        return body, False

    monkeypatch.setattr(th.runner, "execute_suite", execute)
    return tester, system, th, sh, store, resets, forwarded, executions


def test_exact_grader_shape_forwards_id_and_setup_before_returning_ready(pair):
    tester, system, th, sh, store, resets, forwarded, runs = pair
    starting = {"now": "2026-11-01T00:00:00Z"}
    status, response = call(tester, "POST", "/test/setup", {"target_url": TEAM2, "setup": starting})
    assert status == 201 and set(response) == {"session_id"}
    identifier = response["session_id"]
    assert forwarded == [
        (
            "POST",
            "/test/setup",
            {"timeout": 60, "json": {"session_id": identifier, "setup": starting}},
        )
    ]
    assert resets == [(starting["now"], "cra_grading")] and runs == []
    assert (
        store.read("tester", identifier)["status"]
        == store.read("system", identifier)["status"]
        == "ready"
    )
    assert call(tester, "GET", "/test/report", query=response)[0] == 409
    system_report = call(system, "GET", "/test/report", query=response)
    assert system_report[0] == 200 and system_report[1]["session_id"] == identifier
    code = system_report[1]["coverage"]["code"]
    assert code["covered"] is code["total"] is None and code["basis"]
    first = call(tester, "POST", "/test/run", response)
    assert (
        first[0] == 200 and {"session_id", "target_url", "results", "coverage"} <= first[1].keys()
    )
    assert call(tester, "GET", "/test/report", query=response) == first
    assert call(tester, "POST", "/test/run", response)[0] == 409 and runs == [identifier]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        {"target_base_url": TEAM2},
        {"target_url": None},
        {"target_url": "http://169.254.169.254"},
        {"target_url": TEAM2, "setup": []},
    ],
)
def test_invalid_setup_never_forwards_or_creates_a_session(pair, payload):
    tester, _, _, _, store, resets, forwarded, _ = pair
    status, body = call(tester, "POST", "/test/setup", payload)
    assert status == 400 and body["source"] == "tester" and body["message"]
    assert store.rows == {} and resets == forwarded == []


@pytest.mark.parametrize(
    "status,source",
    [(400, "system"), (409, "system"), (500, "system"), (500, "communication"), (503, "unknown")],
)
def test_setup_failure_status_message_source_are_forwarded_and_no_runnable_session_remains(
    pair, monkeypatch, status, source
):
    tester, _, _, _, store, _, _, runs = pair

    def failed(self, *args, **kwargs):
        return SimpleNamespace(
            status_code=status,
            json=lambda: {"message": "Known preparation failure", "source": source},
        )

    monkeypatch.setattr(TargetClient, "request", failed)
    assert call(tester, "POST", "/test/setup", {"target_url": TEAM2}) == (
        status,
        {"message": "Known preparation failure", "source": source},
    )
    assert store.rows == {} and runs == []


def test_system_preparation_failure_and_duplicate_ids(pair, monkeypatch):
    _, system, _, sh, store, _, _, _ = pair

    def failed(*args):
        raise RuntimeError("password=do-not-disclose")

    monkeypatch.setattr(sh, "reset", failed)
    status, body = call(system, "POST", "/test/setup", {"session_id": "direct", "setup": {}})
    assert status == 500 and body == {
        "message": "Could not initialize the session database.",
        "source": "system",
    }
    assert store.read("system", "direct")["status"] == "failed"
    assert call(system, "POST", "/test/setup", {"session_id": "direct", "setup": {}})[0] == 409


def test_tester_waits_for_system_preparation_and_both_reports_are_not_ready(pair, monkeypatch):
    tester, system, _, sh, store, _, _, runs = pair
    entered, release = threading.Event(), threading.Event()

    def prepare(*args):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(sh, "reset", prepare)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(call, tester, "POST", "/test/setup", {"target_url": TEAM2})
        assert entered.wait(5) and not future.done()
        identifier = next(identifier for role, identifier in store.rows if role == "tester")
        for app in [tester, system]:
            assert call(app, "GET", "/test/report", query={"session_id": identifier})[0] == 409
        assert runs == []
        release.set()
        assert future.result() == (201, {"session_id": identifier})


def test_report_is_read_only_and_409_during_setup_or_run_and_concurrent_run_rejected(
    pair, monkeypatch
):
    tester, system, th, sh, store, _, _, _ = pair
    store.rows[("system", "preparing")] = dict(
        role="system", session_id="preparing", status="preparing"
    )
    before = copy.deepcopy(store.rows)
    assert call(system, "GET", "/test/report", query={"session_id": "preparing"})[0] == 409
    assert store.rows == before
    status, ready = call(tester, "POST", "/test/setup", {"target_url": TEAM2})
    entered, release = threading.Event(), threading.Event()

    def execute(target, identifier, deadline, heartbeat):
        entered.set()
        assert release.wait(5)
        return report_body(target, identifier, []), False

    monkeypatch.setattr(th.runner, "execute_suite", execute)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(call, tester, "POST", "/test/run", ready)
        assert entered.wait(5)
        before = copy.deepcopy(store.rows)
        assert call(tester, "GET", "/test/report", query=ready)[0] == 409
        assert store.rows == before
        assert call(tester, "POST", "/test/run", ready)[0] == 409
        release.set()
        assert future.result()[0] == 200


def test_abort_stores_available_results_and_lookup_does_not_repeat_suite(pair, monkeypatch):
    tester, _, th, _, _, _, _, _ = pair
    _, ready = call(tester, "POST", "/test/setup", {"target_url": TEAM2})

    def abort(target, identifier, *args):
        return report_body(
            target,
            identifier,
            [
                {"test_id": "T-1", "outcome": "pass", "message": "Recorded before abort"},
                {
                    "test_id": "T-2",
                    "outcome": "error",
                    "message": "Could not evaluate after abort",
                    "source": "tester",
                },
                {"test_id": "T-3", "outcome": "skip", "message": "Not executed"},
            ],
            message="Synthetic tester abort",
        ), True

    monkeypatch.setattr(th.runner, "execute_suite", abort)
    assert call(tester, "POST", "/test/run", ready) == (
        500,
        {"message": "Synthetic tester abort", "source": "tester"},
    )
    first = call(tester, "GET", "/test/report", query=ready)
    assert first[0] == 200 and [r["outcome"] for r in first[1]["results"]] == [
        "pass",
        "error",
        "skip",
    ]
    assert call(tester, "GET", "/test/report", query=ready) == first
    assert call(tester, "POST", "/test/run", ready)[0] == 409


def test_invalid_run_does_not_consume_ready_session_and_report_requires_id(pair):
    tester, system, *_ = pair
    _, ready = call(tester, "POST", "/test/setup", {"target_url": TEAM2})
    assert call(tester, "POST", "/test/run", {**ready, "unknown": True})[0] == 400
    assert call(tester, "POST", "/test/run", ready)[0] == 200
    for app in [tester, system]:
        assert call(app, "GET", "/test/report")[0] == 400
        assert call(app, "GET", "/test/report", query={"session_id": "missing"})[0] == 404
        schema = app.openapi()
        assert schema["paths"]["/test/setup"]["post"]["responses"]["201"]


def test_pending_session_prevents_another_setup_from_replacing_its_baseline(pair):
    tester, system, _, _, _, resets, forwarded, _ = pair
    _, ready = call(tester, "POST", "/test/setup", {"target_url": TEAM2})
    assert call(tester, "POST", "/test/setup", {"target_url": TEAM2})[0] == 409
    assert call(system, "POST", "/test/setup", {"session_id": "another", "setup": {}})[0] == 409
    assert len(resets) == len(forwarded) == 1
    assert call(tester, "POST", "/test/run", ready)[0] == 200
    assert call(tester, "POST", "/test/setup", {"target_url": TEAM2})[0] == 201


def test_legacy_records_are_retained_but_not_treated_as_ready_current_sessions(pair):
    tester, _, _, _, store, _, _, runs = pair
    legacy = {"role": "tester", "session_id": "old", "status": "ready", "target_base_url": TEAM2}
    store.rows[("tester", "old")] = copy.deepcopy(legacy)
    assert call(tester, "POST", "/test/run", {"session_id": "old"})[0] == 409
    assert call(tester, "GET", "/test/report", query={"session_id": "old"})[0] == 409
    assert store.rows[("tester", "old")] == legacy and runs == []
    assert call(tester, "POST", "/test/setup", {"target_url": TEAM2})[0] == 201


@pytest.mark.parametrize(
    "raw",
    [b'{"target_url":"x","target_url":"y"}', b'{"target_url":NaN}', b"[" * 1500 + b"]" * 1500],
)
def test_malformed_json_returns_required_error_envelope_without_state(pair, raw):
    tester, _, _, _, store, *_ = pair
    status, body = call(tester, "POST", "/test/setup", raw=raw)
    assert status == 400 and body["source"] == "tester" and body["message"]
    assert not store.rows


def test_rejected_field_diagnostics_include_names_and_omit_values(pair, caplog):
    tester, *_ = pair
    status, body = call(
        tester,
        "POST",
        "/test/setup",
        {"target_url": TEAM2, "access_token": "do-not-log-this-value"},
    )
    assert status == 400 and "access_token" in body["message"]
    assert "access_token" in caplog.text and "do-not-log-this-value" not in caplog.text
