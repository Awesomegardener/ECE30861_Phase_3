"""No database/network access: safety gates, deadlines, contract and suite accounting."""

import datetime as dt
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import main
import phase4
import pytest
from autograder.runner import EXPECTED_TESTS, SUITE_FILES, acceptance_id
from fastapi import HTTPException
from pydantic import ValidationError


@pytest.mark.parametrize(
    "model,field",
    [
        (phase4.IncidentCreate, "awareness_at"),
        (phase4.IncidentUpdate, "fix_available_at"),
        (phase4.SubmissionCreate, "submitted_at"),
    ],
)
def test_incident_models_reject_invalid_timestamps(model, field, invalid_clock_input):
    body = dict(classification="mandatory", rationale="reason", stage="early_warning")
    body[field] = invalid_clock_input
    with pytest.raises(ValidationError):
        model(**body)


@pytest.mark.parametrize(
    "mode,configured,actual",
    [
        ("false", "cra_grading", "cra_grading"),
        ("true", "cra_phase3", "cra_phase3"),
        ("true", "cra_grading", "cra_phase3"),
        ("true", "cra_test", "cra_phase3"),
        ("true", "other", "other"),
    ],
)
def test_fault_injection_refuses_retained_or_unapproved_database(
    monkeypatch, mode, configured, actual
):
    monkeypatch.setenv("VULNERABILITY_TEST_MODE", mode)
    monkeypatch.setenv("VULNERABILITY_SOURCE", "fixture")
    monkeypatch.setenv("VULNERABILITY_TEST_DATABASE", configured)
    statements = []

    class Cursor:
        def execute(self, query):
            statements.append(query)

        def fetchone(self):
            return {"name": actual}

    with pytest.raises(HTTPException) as exc:
        phase4.require_test_source(Cursor())
    assert exc.value.status_code == 503
    assert exc.value.detail["error"]["code"] == "VULNERABILITY_SOURCE_UNREACHABLE"
    assert all(query.startswith("SELECT") for query in statements)


@pytest.mark.parametrize("database_name", ["cra_grading", "cra_test"])
def test_opt_in_disposable_source_is_accepted(monkeypatch, database_name):
    monkeypatch.setenv("VULNERABILITY_SOURCE", "fixture")
    monkeypatch.setenv("VULNERABILITY_TEST_MODE", "true")
    monkeypatch.setenv("VULNERABILITY_TEST_DATABASE", database_name)

    class Cursor:
        def execute(self, query):
            assert query == "SELECT current_database() AS name"

        def fetchone(self):
            return {"name": database_name}

    phase4.require_test_source(Cursor())


def test_retained_database_startup_refused_before_any_ddl(monkeypatch):
    statements = []

    class Cursor:
        def execute(self, query, parameters=None):
            statements.append(query)

        def fetchone(self):
            return {"name": "cra_phase3"}

    class Connection:
        @contextmanager
        def cursor(self):
            yield Cursor()

    @contextmanager
    def database(**kwargs):
        yield Connection()

    monkeypatch.setattr(main, "database", database)
    with pytest.raises(RuntimeError, match="retained"):
        main.init_db()
    assert all(str(q).startswith("SELECT") for q in statements)


@pytest.mark.parametrize("number", range(4, 8))
def test_new_acceptance_classification(number):
    assert acceptance_id(f"test_ac{number:02d}_example[x]") == f"AC-{number:02d}"


def test_hosted_suite_count_matches_actual_collection():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "pytest", *SUITE_FILES, "--collect-only", "-q"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if "::test_" in line]
    assert len(lines) == len(set(lines)) == EXPECTED_TESTS
    assert sum(line.startswith("cra-service/test_api.py::") for line in lines) == 157
    assert sum(line.startswith("cra-service/test_phase4_api.py::") for line in lines) == 196


def test_late_submission_stays_overdue_when_clock_moves_backwards():
    due = dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc)
    result = phase4.deadline(due, due + dt.timedelta(seconds=1), due - dt.timedelta(days=1))
    assert result["status"] == "overdue"


@pytest.mark.parametrize(
    "model,field",
    [
        (phase4.IncidentCreate, "awareness_at"),
        (phase4.IncidentUpdate, "fix_available_at"),
        (phase4.SubmissionCreate, "submitted_at"),
    ],
)
def test_all_incident_timestamp_fields_preserve_valid_offsets(model, field, valid_clock_case):
    value, expected = valid_clock_case
    body = dict(classification="mandatory", rationale="reason", stage="early_warning")
    body[field] = value
    parsed = model(**body)
    assert phase4.stamp(getattr(parsed, field)) == expected


def test_utc_underflow_is_a_validation_error():
    value = dt.datetime(1, 1, 1, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    with pytest.raises(HTTPException) as exc:
        phase4.utc(value)
    assert exc.value.status_code == 400
