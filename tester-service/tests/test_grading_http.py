"""Public system coverage is session-scoped, observable and independent of tests."""

import os
import uuid

import pytest
import requests
from test_http import call

pytestmark = pytest.mark.skipif(
    os.getenv("HARNESS_GRADING_INTEGRATION") != "1", reason="Fresh instrumented system required"
)


def test_system_report_measures_direct_requests_without_tester_or_private_credentials():
    base = os.environ["HARNESS_SYSTEM_URL"]
    assert base.startswith("http://127.0.0.1:")
    first = "coverage-" + uuid.uuid4().hex
    call(base, "system", "POST", "/test/setup", 201, json={"session_id": first, "setup": {}})
    initial = call(base, "system", "GET", "/test/report", params={"session_id": first})
    assert initial["coverage"]["code"]["covered"] == 0 and initial["coverage"]["code"]["total"] > 0
    assert initial == call(base, "system", "GET", "/test/report", params={"session_id": first})
    created = requests.post(
        base + "/api/v1/releases",
        json={"product": "Measured", "version": "1", "support_end_date": "2099-01-01"},
        headers={"X-User-Id": "isolated-coverage-test", "X-Test-Session-Id": first},
        timeout=10,
    )
    assert created.status_code == 201
    measured = call(base, "system", "GET", "/test/report", params={"session_id": first})
    assert 0 < measured["coverage"]["code"]["covered"] <= measured["coverage"]["code"]["total"]
    assert measured == call(base, "system", "GET", "/test/report", params={"session_id": first})
    second = "coverage-" + uuid.uuid4().hex
    call(base, "system", "POST", "/test/setup", 201, json={"session_id": second, "setup": {}})
    assert measured == call(base, "system", "GET", "/test/report", params={"session_id": first})
    fresh = call(base, "system", "GET", "/test/report", params={"session_id": second})
    assert fresh["coverage"]["code"]["covered"] == 0
    stale = requests.get(
        base + "/api/v1/releases/not-present", headers={"X-Test-Session-Id": first}, timeout=10
    )
    assert stale.status_code == 409 and stale.json()["source"] == "system"
    assert fresh == call(base, "system", "GET", "/test/report", params={"session_id": second})
