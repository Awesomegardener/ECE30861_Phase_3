"""Prose rules: dispatch coverage, complete abort journals and error attribution."""

import json
from types import SimpleNamespace

import pytest
import requests
from autograder import pytest_guard
from autograder.client import TargetClient
from autograder.config import TEAM2, HarnessError, Settings
from autograder.coverage import acceptance_coverage
from autograder.reporting import results_from_journal


def test_acceptance_denominator_is_pod_criteria_and_is_independent_of_response_success():
    inputs = [
        {"test_id": "test_ac01_shared_release_cases", "method": "POST", "path": "/api/v1/releases"}
        for _ in range(4)
    ] + [
        {
            "test_id": "test_ac01_support_boundary",
            "method": "GET",
            "path": "/api/v1/releases/{releaseId}",
        }
        for _ in range(3)
    ]
    success = acceptance_coverage([{**item, "status": 200} for item in inputs])
    failed = acceptance_coverage([{**item, "status": 500} for item in inputs])
    assert success == failed and success["criteria"] == ["AC-01"]
    assert success["covered"] == 1 and success["total"] == 10
    assert acceptance_coverage(inputs[:-1])["covered"] == 0
    assert acceptance_coverage([])["total"] == 10


def test_abort_journal_keeps_results_once_and_marks_active_error_remaining_skip(tmp_path):
    journal = tmp_path / "results.jsonl"
    events = [
        {"event": "start", "test_id": "one"},
        {
            "event": "result",
            "test_id": "one",
            "outcome": "pass",
            "message": "Expected error received",
        },
        {"event": "start", "test_id": "two"},
    ]
    journal.write_text("\n".join(json.dumps(e) for e in events) + '\n{"event":')
    results, complete = results_from_journal(["one", "two", "three"], journal, aborted=True)
    assert not complete
    assert [item["test_id"] for item in results] == ["one", "two", "three"]
    assert [item["outcome"] for item in results] == ["pass", "error", "skip"]
    assert results[1]["source"] == "tester"


@pytest.mark.parametrize(
    "source,outcome,expected",
    [
        ("system", "failed", "error"),
        ("communication", "failed", "error"),
        (None, "failed", "fail"),
        ("system", "passed", "pass"),
    ],
)
def test_result_failure_location_and_expected_project_errors(
    monkeypatch, source, outcome, expected
):
    recorded = []
    monkeypatch.setattr(pytest_guard, "journal", recorded.append)
    identifier = "cra-service/test_api.py::test_example"
    monkeypatch.setattr(pytest_guard, "LAST_RESPONSE", {identifier: {"source": source}})
    pytest_guard.pytest_runtest_logreport(
        SimpleNamespace(
            nodeid=identifier,
            when="call",
            passed=outcome == "passed",
            failed=outcome == "failed",
            skipped=False,
            longrepr=SimpleNamespace(reprcrash=SimpleNamespace(message="assert 500 == 200")),
        )
    )
    assert recorded[0]["outcome"] == expected
    if expected == "error":
        assert recorded[0]["source"] == source
    else:
        assert "source" not in recorded[0]


@pytest.fixture
def target():
    settings = Settings(
        "tester", True, True, "unused", TEAM2, frozenset({TEAM2}), "cra_grading", 10
    )
    return TargetClient(settings, TEAM2)


def test_setup_no_response_is_communication_error_without_secret_details(target, monkeypatch):
    def failed(*args, **kwargs):
        raise requests.Timeout("password=do-not-log")

    monkeypatch.setattr(requests.Session, "request", failed)
    with pytest.raises(HarnessError) as error:
        target.setup("id", {})
    assert error.value.status == 500 and error.value.source == "communication"
    assert "password" not in error.value.message


@pytest.mark.parametrize("body", [{"session_id": "wrong"}, [], {"session_id": None}])
def test_setup_requires_same_forwarded_id(target, monkeypatch, body):
    monkeypatch.setattr(
        target, "request", lambda *a, **k: SimpleNamespace(status_code=201, json=lambda: body)
    )
    with pytest.raises(HarnessError) as error:
        target.setup("expected", {})
    assert error.value.status == 500 and error.value.source == "system"


@pytest.mark.parametrize(
    "code",
    [
        {"covered": True, "total": 1, "basis": "invalid boolean"},
        {"covered": 3, "total": 2, "basis": "invalid counts"},
        {"covered": None, "total": 2, "basis": "partial null"},
        {"covered": 0, "total": 2, "basis": ""},
    ],
)
def test_invalid_system_measurements_are_unavailable_not_fabricated(target, monkeypatch, code):
    monkeypatch.setattr(
        target,
        "request",
        lambda *a, **k: SimpleNamespace(
            status_code=200, json=lambda: {"session_id": "id", "coverage": {"code": code}}
        ),
    )
    measured = target.code_coverage("id", float("inf"))
    assert measured["covered"] is measured["total"] is None
    assert measured["basis"]
