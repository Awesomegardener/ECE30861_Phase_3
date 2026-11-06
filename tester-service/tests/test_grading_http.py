"""Cloud-compatible coverage path: live requests, independent role sessions.

Run only against a new disposable docker-compose.grading.yml stack. No mounts,
shutdown flush or metadata import is used before reading measured reports.
"""

import base64
import gzip
import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest
import requests
from autograder.measured_coverage import logical_contexts
from autograder.runner import EXPECTED_TESTS

pytestmark = pytest.mark.skipif(
    os.getenv("HARNESS_GRADING_INTEGRATION") != "1",
    reason="Disposable instrumented grading stack required",
)


@pytest.fixture(scope="module")
def urls():
    result = {role: os.environ["HARNESS_" + role.upper() + "_URL"] for role in ("system", "tester")}
    assert all(value.startswith("http://127.0.0.1:") for value in result.values())
    return result


def call(base, method, route, status=200, **kwargs):
    with requests.Session() as session:
        session.trust_env = False
        response = session.request(
            method, base + route, timeout=660, allow_redirects=False, **kwargs
        )
    assert response.status_code == status, response.text[:1000]
    return response.json()


@pytest.mark.parametrize("role", ["system", "tester"])
def test_live_measured_workflow_and_openapi(urls, role):
    base = urls[role]
    discovery = call(base, "GET", "/test")
    assert discovery["coverage_enabled"] is True
    assert discovery["coverage_ready"] is (role == "system")
    schema = call(base, "GET", "/openapi.json")
    assert "201" in schema["paths"]["/test/setup"]["post"]["responses"]
    assert "200" not in schema["paths"]["/test/setup"]["post"]["responses"]
    assert not any(path.startswith("/internal/") for path in schema["paths"])
    identifier = "live-" + role + "-" + uuid.uuid4().hex
    setup = call(base, "POST", "/test/setup", 201, json={"session_id": identifier})
    assert setup["session_id"] == identifier
    outcome = call(base, "POST", "/test/run", json={"session_id": identifier})
    assert outcome["result"] == "pass", outcome
    report = call(base, "GET", "/test/report?session_id=" + identifier)
    assert report["summary"]["passed"] == EXPECTED_TESTS
    for kind in ("code", "component", "system"):
        metric = report["coverage"][kind]
        assert metric["status"] == "measured" and 0 < metric["covered"] <= metric["total"]
    provenance = report["coverage"]["code"]["provenance"]
    assert provenance["session_id"] == identifier and provenance["role"] == role
    assert provenance["attributed_tests"] == EXPECTED_TESTS
    artifact = report["coverage"]["code"]["trace_artifact"]
    raw = gzip.decompress(base64.b64decode(artifact["data"]))
    assert len(raw) < 10 * 1024 * 1024  # Bounded file-level artifact, not repeated region contexts.
    assert hashlib.sha256(raw).hexdigest() == artifact["sha256"] == provenance["trace_sha256"]
    trace = json.loads(raw)
    assert set(Path(p).name for p in trace["files"]) == set(
        Path(p).name for p in provenance["source_sha256"]
    )
    assert (
        sum(len(data["executed_lines"]) for data in trace["files"].values())
        == report["coverage"]["code"]["covered"]
    )
    for data in trace["files"].values():
        for line in data["executed_lines"]:
            assert any(
                c.startswith(provenance["run_id"] + "|cra-service/")
                for c in logical_contexts(data)[line]
            )
    # Cached retry preserves this window and never starts another measurement.
    assert call(base, "POST", "/test/run", json={"session_id": identifier}) == outcome
    assert call(base, "GET", "/test/report?session_id=" + identifier) == report
    evidence = Path(os.getenv("HARNESS_EVIDENCE_DIR", "artifacts/grading"))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{role}-report.json").write_text(json.dumps(report, indent=2))


def test_control_requires_secret_and_does_not_infer_session_workflow(urls):
    for operation in ("start", "finish", "abort"):
        result = call(
            urls["system"],
            "POST",
            "/internal/coverage/" + operation,
            403,
            json={"session_id": "known-but-not-a-credential"},
        )
        assert result["error"]["code"] == "COVERAGE_FORBIDDEN"
    # Role namespaces stay independent; no undocumented shared session semantics.
    identifier = "tester-only-" + uuid.uuid4().hex
    call(urls["tester"], "POST", "/test/setup", 201, json={"session_id": identifier})
    call(urls["system"], "GET", "/test/report?session_id=" + identifier, 404)


def test_consecutive_measurements_do_not_mix_sessions():
    evidence = Path(os.getenv("HARNESS_EVIDENCE_DIR", "artifacts/grading"))
    reports = [
        json.loads((evidence / f"{role}-report.json").read_text()) for role in ("system", "tester")
    ]
    ids = [r["coverage"]["code"]["provenance"]["run_id"] for r in reports]
    assert ids[0] != ids[1]
    for index, report in enumerate(reports):
        raw = json.loads(
            gzip.decompress(base64.b64decode(report["coverage"]["code"]["trace_artifact"]["data"]))
        )
        contexts = {
            c
            for data in raw["files"].values()
            for values in data["contexts"].values()
            for c in values
        }
        # JSON context lists can include all contexts for a line in coverage.py;
        # counted execution must have this run's witness, never the other run.
        for data in raw["files"].values():
            for line in data["executed_lines"]:
                assert any(c.startswith(ids[index] + "|") for c in logical_contexts(data)[line])
        assert not any(c.startswith(ids[1 - index] + "|") for c in contexts)
