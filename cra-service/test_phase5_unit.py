"""Phase 5 unit and code-inspection checks that need no running service."""

import re
from pathlib import Path

import audit
import pytest
import reports
from fastapi import HTTPException

SERVICE = Path(__file__).resolve().parent


def test_ac09_no_code_path_updates_or_deletes_audit_events():
    """AC-09 code inspection: the application never edits or removes audit rows.

    The only bulk removal is the test reset's TRUNCATE, which the database
    trigger restricts to the disposable cra_grading/cra_test databases.
    """
    offenders = []
    for path in SERVICE.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in (r"UPDATE\s+audit_events", r"DELETE\s+FROM\s+audit_events"):
            if re.search(pattern, text, re.IGNORECASE):
                offenders.append((path.name, pattern))
    assert offenders == []
    truncates = [
        path.name
        for path in SERVICE.rglob("*.py")
        if not path.name.startswith("test_")
        and re.search(r"TRUNCATE\s+audit_events", path.read_text(encoding="utf-8"))
    ]
    assert truncates == ["audit.py"]


def test_ac09_database_enforces_immutability():
    schema = "\n".join(audit.SCHEMA_STATEMENTS)
    assert "BEFORE UPDATE OR DELETE ON audit_events" in schema
    assert "BEFORE TRUNCATE ON audit_events" in schema
    assert "current_database() NOT IN ('cra_grading', 'cra_test')" in schema


def test_audit_rejects_unknown_actions():
    with pytest.raises(ValueError):
        audit.record(
            None,
            at=None,
            user_id="u",
            action="RELEASE_DELETED",
            entity_type="release",
            entity_id="r",
        )


def test_stage_fields_match_pod_q1():
    assert reports.REQUIRED["early_warning"] == ("member_states",)
    assert reports.OPTIONAL["vulnerability_notification"] == ("sensitivity",)
    assert reports.OPTIONAL["final_report"] == ("malicious_actor_information",)
    assert len(reports.ALL_FIELDS) == 12


@pytest.mark.parametrize(
    ("data", "missing"),
    [
        ({}, ["member_states"]),
        ({"member_states": None}, ["member_states"]),
        ({"member_states": []}, ["member_states"]),
        ({"member_states": [""]}, []),
        ({"member_states": ["DE"]}, []),
    ],
)
def test_missing_member_states(data, missing):
    assert reports.missing_fields("early_warning", data) == missing


def test_missing_fields_keep_contract_order():
    data = {"user_mitigations": " ", "product_information": "P"}
    assert reports.missing_fields("vulnerability_notification", data) == [
        "exploit_nature",
        "vulnerability_nature",
        "corrective_measures_taken",
        "user_mitigations",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"severity": "has\x00nul"},
        {"severity": 1.5},
        {"unknown": "x"},
        {"member_states": ["DE"]},
    ],
)
def test_validate_data_rejects_bad_final_report_fields(payload):
    with pytest.raises(HTTPException) as caught:
        reports.validate_data("final_report", payload)
    assert caught.value.status_code == 400


def test_validate_data_returns_payload_unchanged():
    payload = {"severity": "  high  ", "impact": None}
    assert reports.validate_data("final_report", payload) is payload
