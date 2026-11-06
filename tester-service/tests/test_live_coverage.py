"""Measurement isolation and lease/auth tests without network or a database."""

import asyncio
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from autograder.config import HarnessError, Settings
from autograder.live_coverage import LiveCoverage, LiveCoverageMiddleware
from starlette.requests import Request


def test_active_collector_snapshot_excludes_startup_and_other_run_branches(tmp_path):
    import coverage
    from autograder.live_coverage import snapshot_report

    source = tmp_path / "sample.py"
    source.write_text("def choose(flag):\n    if flag:\n        return 11\n    return 22\n")
    collector = coverage.Coverage(
        data_file=None, branch=True, config_file=False, include=[str(source)]
    )
    collector.start()
    try:
        spec = importlib.util.spec_from_file_location("sample", source)
        sample = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sample)
        collector.switch_context("other|cra-service/test_api.py::test_other")
        assert sample.choose(False) == 22
        collector.switch_context("current|cra-service/test_api.py::test_current")
        assert sample.choose(True) == 11
        collector.switch_context("unattributed")
        path = tmp_path / "snapshot.json"
        snapshot_report(collector, [source], path, "current")
        result = next(iter(json.loads(path.read_text())["files"].values()))
        assert set(result["executed_lines"]) == {2, 3}
        assert [2, 4] not in result["executed_branches"]
        assert result["executed_branches"] == [[2, 3]]
        # Original collector remains active for later sessions/worker threads.
        collector.switch_context("later|cra-service/test_api.py::test_later")
        assert sample.choose(False) == 22
        snapshot_report(collector, [source], path, "later")
        later = next(iter(json.loads(path.read_text())["files"].values()))
        assert set(later["executed_lines"]) == {2, 4}
    finally:
        collector.stop()


def test_multiline_condition_contexts_bind_to_real_logical_statement(tmp_path):
    import coverage
    from autograder.live_coverage import snapshot_report
    from autograder.measured_coverage import logical_contexts

    source = tmp_path / "multiline.py"
    source.write_text(
        "def choose(a, b):\n    if (\n        a\n        and b\n    ):\n        return 11\n    return 22\n"
    )
    collector = coverage.Coverage(
        data_file=None, branch=True, config_file=False, include=[str(source)]
    )
    collector.start()
    try:
        spec = importlib.util.spec_from_file_location("multiline", source)
        sample = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sample)
        context = "current|cra-service/test_api.py::test_current"
        collector.switch_context(context)
        assert sample.choose(True, True) == 11
        collector.switch_context("unattributed")
        path = tmp_path / "trace.json"
        snapshot_report(collector, [source], path, "current")
        data = next(iter(json.loads(path.read_text())["files"].values()))
        assert 2 in data["executed_lines"] and 7 in data["missing_lines"]
        normalized = logical_contexts(data)
        assert context in normalized[2]
        assert all(context in normalized[line] for line in data["executed_lines"])
        assert [2, 6] in data["executed_branches"] and [2, 7] not in data["executed_branches"]
    finally:
        collector.stop()


@pytest.fixture
def manager():
    class Collector:
        contexts = []

        def switch_context(self, value):
            self.contexts.append(value)

    settings = Settings(
        "system",
        True,
        True,
        "offline",
        "http://127.0.0.1:8080",
        frozenset({"http://127.0.0.1:8080"}),
        "cra_grading",
        600,
        coverage_enabled=True,
        coverage_token="x" * 40,
    )
    return LiveCoverage(Collector(), Path("unused"), settings, lambda _: None)


def test_authentication_never_uses_session_id_as_a_credential(manager):
    with pytest.raises(HarnessError) as error:
        manager.authorize(
            Request({"type": "http", "headers": [(b"x-cra-coverage-key", b"session-id")]})
        )
    assert error.value.status == 403
    manager.authorize(Request({"type": "http", "headers": [(b"x-cra-coverage-key", b"x" * 40)]}))


def test_abort_then_same_session_uses_new_nonce_and_rejects_old_window(manager):
    async def run():
        identity = {"role": "tester", "session_id": "same-id", "timeout": 600}
        first = await manager.start(identity)
        with pytest.raises(HarnessError):
            await manager.start({**identity, "session_id": "other-id"})
        with pytest.raises(HarnessError):
            await manager.end(
                {"run_id": first["run_id"], "report": {"role": "system", "session_id": "same-id"}}
            )
        await manager.end({"run_id": first["run_id"]}, abort=True)
        second = await manager.start(identity)
        assert first["run_id"] != second["run_id"]
        assert first["request_token"] != second["request_token"]
        with pytest.raises(HarnessError):
            await manager.end({"run_id": first["run_id"]}, abort=True)

    asyncio.run(run())


def test_expired_window_cannot_be_reused(manager):
    clock = [0]
    manager.monotonic = lambda: clock[0]

    async def run():
        first = await manager.start({"role": "tester", "session_id": "one", "timeout": 1})
        clock[0] = 32
        assert manager.current() is None
        second = await manager.start({"role": "system", "session_id": "two", "timeout": 1})
        assert second["run_id"] != first["run_id"]

    asyncio.run(run())


def test_recovered_parent_releases_old_window_without_crediting_it_to_new_session(manager):
    async def run():
        first = await manager.start({"role": "tester", "session_id": "old", "timeout": 600})
        manager.session_running = lambda role, identifier: identifier == "new"
        second = await manager.start({"role": "tester", "session_id": "new", "timeout": 600})
        assert second["run_id"] != first["run_id"]
        with pytest.raises(HarnessError):
            await manager.end({"run_id": first["run_id"]}, abort=True)

    asyncio.run(run())


def test_adapter_parent_does_not_deadlock_child_and_concurrent_contexts_do_not_mix(manager):
    observed = []

    async def endpoint(scope, receive, send):
        if scope["path"] == "/test/run":
            await asyncio.gather(*[wrapper(domain(n), receive, send) for n in range(3)])
        else:
            before = manager.collector.contexts[-1]
            await asyncio.sleep(0)
            assert manager.collector.contexts[-1] == before
            observed.append(before)

    wrapper = LiveCoverageMiddleware(endpoint, manager)

    def domain(n):
        return {
            "type": "http",
            "path": "/api/v1/releases",
            "headers": [
                (b"x-cra-coverage-run", manager.active["run_id"].encode()),
                (b"x-cra-coverage-request", manager.active["request_token"].encode()),
                (b"x-cra-coverage-test", f"cra-service/test_api.py::test_{n}".encode()),
            ],
        }

    async def run():
        window = await manager.start({"role": "tester", "session_id": "test", "timeout": 10})
        await asyncio.wait_for(
            wrapper({"type": "http", "path": "/test/run", "headers": []}, None, None), 1
        )
        assert observed == [
            window["run_id"] + f"|cra-service/test_api.py::test_{n}" for n in range(3)
        ]

    asyncio.run(run())


def test_unapproved_target_still_fails_before_coverage_configuration(manager):
    from autograder.coverage_client import CoverageClient

    settings = replace(manager.settings, coverage_targets=frozenset({"https://evil.example"}))
    with pytest.raises(HarnessError) as error:
        CoverageClient(settings, "https://evil.example", {"role": "tester", "session_id": "test"})
    assert error.value.code == "INVALID_TARGET"


def test_coverage_environment_fails_closed_and_redacts_secret_repr(monkeypatch):
    monkeypatch.setenv("AUTOGRADER_COVERAGE_ENABLED", "true")
    monkeypatch.delenv("AUTOGRADER_COVERAGE_TOKEN", raising=False)
    monkeypatch.delenv("AUTOGRADER_COVERAGE_TARGETS", raising=False)
    with pytest.raises(ValueError):
        Settings.environment("tester")
    monkeypatch.setenv("AUTOGRADER_COVERAGE_TOKEN", "do-not-print-" * 4)
    monkeypatch.setenv("AUTOGRADER_DEFAULT_TARGET", "https://approved.example")
    monkeypatch.setenv("AUTOGRADER_APPROVED_TARGETS", "https://approved.example")
    monkeypatch.setenv("AUTOGRADER_COVERAGE_TARGETS", "https://other.example")
    with pytest.raises(ValueError):
        Settings.environment("tester")
    monkeypatch.setenv("AUTOGRADER_COVERAGE_TARGETS", "https://approved.example")
    assert "do-not-print" not in repr(Settings.environment("tester"))


def test_wrong_instance_nonce_is_refused_before_domain_execution(manager):
    reached = []
    messages = []

    async def endpoint(*args):
        reached.append(True)

    async def send(message):
        messages.append(message)

    async def run():
        window = await manager.start({"role": "tester", "session_id": "one", "timeout": 10})
        scope = {
            "type": "http",
            "path": "/api/v1/test/reset",
            "headers": [
                (b"x-cra-coverage-run", window["run_id"].encode()),
                (b"x-cra-coverage-request", b"wrong-instance-token"),
                (b"x-cra-coverage-test", b"cra-service/test_api.py::test_reset"),
            ],
        }
        await LiveCoverageMiddleware(endpoint, manager)(scope, None, send)

    asyncio.run(run())
    assert not reached and messages[0]["status"] == 409


def test_measurement_failure_retains_real_test_outcomes(manager, monkeypatch):
    from autograder.coverage import unavailable_coverage
    from autograder.runner import Runner

    settings = replace(
        manager.settings,
        role="tester",
        coverage_targets=frozenset({manager.settings.default_target}),
    )
    runner = Runner(settings)
    checks = [{"id": "real-case", "passed": True}]

    class Client:
        def __init__(self, *args):
            pass

        def start(self):
            return {"run_id": "window", "request_token": "short-lived"}

        def finish(self, result):
            raise HarnessError(503, "COVERAGE_UNAVAILABLE", "Target measurement failed")

        def abort(self):
            pass

    monkeypatch.setattr("autograder.runner.CoverageClient", Client)
    monkeypatch.setattr(
        runner,
        "_execute",
        lambda *args: {
            "result": "pass",
            "checks": checks,
            "summary": {"passed": 1},
            "coverage": unavailable_coverage(),
        },
    )
    result = runner.execute(
        settings.default_target, lambda: None, {"role": "tester", "session_id": "one"}
    )
    assert result["result"] == "error" and result["checks"] == checks
    assert result["summary"]["passed"] == 1
    assert result["coverage"]["code"]["status"] == "unavailable"


def test_child_receives_only_short_lived_coverage_token(manager, monkeypatch):
    from autograder.runner import Runner

    monkeypatch.setenv("AUTOGRADER_COVERAGE_TOKEN", "do-not-pass-service-key")
    monkeypatch.setenv("DATABASE_URL", "do-not-pass-database")
    captured = {}

    def popen(*args, **kwargs):
        captured.update(kwargs["env"])
        raise RuntimeError("Stop before any child/network execution")

    monkeypatch.setattr("autograder.runner.subprocess.Popen", popen)
    with pytest.raises(RuntimeError):
        Runner(manager.settings)._execute(
            manager.settings.default_target,
            lambda: None,
            {"run_id": "window", "request_token": "short-lived"},
        )
    assert captured["CRA_COVERAGE_REQUEST_TOKEN"] == "short-lived"
    assert "AUTOGRADER_COVERAGE_TOKEN" not in captured and "DATABASE_URL" not in captured
