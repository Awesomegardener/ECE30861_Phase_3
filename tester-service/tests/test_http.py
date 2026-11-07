"""Live prose-contract tests; only a new isolated Compose project is allowed."""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
import yaml
from autograder.config import TEAM2
from autograder.runner import EXPECTED_TESTS
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("HARNESS_INTEGRATION") != "1", reason="Fresh isolated Compose stack required"
)


@pytest.fixture(scope="module")
def urls():
    result = {role: os.environ["HARNESS_" + role.upper() + "_URL"] for role in ["tester", "system"]}
    assert all(value.startswith("http://127.0.0.1:") for value in result.values())
    return result


def call(base, role, method, path, status=200, **kwargs):
    with requests.Session() as client:
        client.trust_env = False
        response = client.request(method, base + path, timeout=660, allow_redirects=False, **kwargs)
    assert response.status_code == status, response.text[:1000]
    data = response.json()
    spec = yaml.safe_load(
        (
            ROOT
            / "docs"
            / ("autograder-openapi.yaml" if role == "tester" else "system-test-openapi.yaml")
        ).read_text()
    )
    operation = spec["paths"][path.split("?")[0]][method.lower()]
    code = str(status) if str(status) in operation["responses"] else "default"
    pointer = path.split("?")[0].replace("/", "~1")
    registry = Registry().with_resource("urn:contract", DRAFT202012.create_resource(spec))
    Draft202012Validator(
        {
            "$ref": f"urn:contract#/paths/{pointer}/{method.lower()}/responses/{code}/content/application~1json/schema"
        },
        registry=registry,
    ).validate(data)
    return data


def check_suite(body):
    assert len(body["results"]) == EXPECTED_TESTS
    assert len({item["test_id"] for item in body["results"]}) == EXPECTED_TESTS
    for item in body["results"]:
        assert item["test_id"] and item["message"].strip()
        if item["outcome"] == "error":
            assert item["source"] in {"tester", "system", "communication", "unknown"}
    for metric in body["coverage"].values():
        covered, total = metric["covered"], metric["total"]
        assert (
            (covered, total) == (None, None)
            or type(covered) is int
            and type(total) is int
            and 0 <= covered <= total
        )
        assert metric["basis"].strip()
    assert (
        body["coverage"]["component"]["covered"] is body["coverage"]["component"]["total"] is None
    )


def workflow(urls, target):
    # This literal is the exact rejected request when target == TEAM2.
    payload = {"target_url": target}
    ready = call(urls["tester"], "tester", "POST", "/test/setup", 201, json=payload)
    identifier = ready["session_id"]
    call(urls["tester"], "tester", "GET", "/test/report", 409, params=ready)
    call(urls["tester"], "tester", "POST", "/test/setup", 409, json=payload)
    call(
        urls["system"],
        "system",
        "POST",
        "/test/setup",
        409,
        json={"session_id": "conflict-" + uuid.uuid4().hex, "setup": {}},
    )
    before = call(urls["system"], "system", "GET", "/test/report", params=ready)
    assert before == call(urls["system"], "system", "GET", "/test/report", params=ready)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(call, urls["tester"], "tester", "POST", "/test/run", json=ready)
        time.sleep(0.1)
        call(urls["tester"], "tester", "GET", "/test/report", 409, params=ready)
        call(urls["tester"], "tester", "POST", "/test/run", 409, json=ready)
        report = future.result()
    check_suite(report)
    assert report["session_id"] == identifier and report["target_url"] == target
    assert all(result["outcome"] == "pass" for result in report["results"]), [
        r for r in report["results"] if r["outcome"] != "pass"
    ][:3]
    assert report == call(urls["tester"], "tester", "GET", "/test/report", params=ready)
    assert report == call(urls["tester"], "tester", "GET", "/test/report", params=ready)
    call(urls["tester"], "tester", "POST", "/test/run", 409, json=ready)
    system = call(urls["system"], "system", "GET", "/test/report", params=ready)
    assert system["coverage"]["code"] == report["coverage"]["code"]
    assert "results" not in system and set(system["coverage"]) == {"code"}
    code = report["coverage"]["code"]
    if os.getenv("HARNESS_CONTRACT_INTEGRATION") == "1":
        assert 0 < code["covered"] <= code["total"]
        assert code["provenance"]["session_id"] == identifier
        assert (
            report["coverage"]["system"]["covered"] == 7
            and report["coverage"]["system"]["total"] == 10
        )
    out = Path(os.getenv("HARNESS_EVIDENCE_DIR", ROOT / "artifacts/contract"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "tester-report.json").write_text(json.dumps(report, indent=2))
    (out / "system-report.json").write_text(json.dumps(system, indent=2))
    return ready, report


def test_prepared_remote_suite_and_both_reports(urls):
    workflow(urls, os.getenv("HARNESS_TARGET_URL", "http://api:8080"))


@pytest.mark.skipif(
    os.getenv("HARNESS_CONTRACT_INTEGRATION") != "1",
    reason="Internal DNS/TLS route for exact grader URL required",
)
def test_exact_rejected_grader_request_only_reaches_isolated_target(urls):
    ready, report = workflow(urls, TEAM2)
    forwarded = json.loads(
        (Path(os.environ["HARNESS_CONTROL_DIR"]) / "last-setup.json").read_text()
    )
    assert forwarded == {"session_id": ready["session_id"], "setup": {}}
    assert report["target_url"] == TEAM2


def test_system_direct_setup_report_and_duplicate_session(urls):
    identifier = "direct-" + uuid.uuid4().hex
    prepared = {"session_id": identifier, "setup": {}}
    assert call(urls["system"], "system", "POST", "/test/setup", 201, json=prepared) == {
        "session_id": identifier
    }
    first = call(urls["system"], "system", "GET", "/test/report", params={"session_id": identifier})
    assert first == call(
        urls["system"], "system", "GET", "/test/report", params={"session_id": identifier}
    )
    call(urls["system"], "system", "POST", "/test/setup", 409, json=prepared)


@pytest.mark.parametrize("role", ["tester", "system"])
def test_required_bodies_errors_and_unknown_sessions(urls, role):
    for body in [{}, None, [], {"session_id": "x"}, {"target_base_url": TEAM2}]:
        error = call(urls[role], role, "POST", "/test/setup", 400, json=body)
        assert error["source"] == role
    call(urls[role], role, "GET", "/test/report", 400)
    call(urls[role], role, "GET", "/test/report", 404, params={"session_id": "does-not-exist"})
    if role == "tester":
        call(urls[role], role, "POST", "/test/run", 400, json={})
        call(urls[role], role, "POST", "/test/run", 404, json={"session_id": "does-not-exist"})


@pytest.mark.skipif(
    os.getenv("HARNESS_CONTRACT_INTEGRATION") != "1",
    reason="Isolated failure injection bridge required",
)
def test_setup_failure_is_forwarded_and_does_not_create_runnable_session(urls):
    control = Path(os.environ["HARNESS_CONTROL_DIR"])
    (control / "fault.json").write_text(json.dumps({"setup_status": 500}))
    try:
        assert call(
            urls["tester"], "tester", "POST", "/test/setup", 500, json={"target_url": TEAM2}
        ) == {"message": "Synthetic preparation failure", "source": "system"}
        failed = json.loads((control / "last-setup.json").read_text())
        call(
            urls["tester"],
            "tester",
            "POST",
            "/test/run",
            404,
            json={"session_id": failed["session_id"]},
        )
    finally:
        (control / "fault.json").unlink(missing_ok=True)


@pytest.mark.skipif(
    os.getenv("HARNESS_CONTRACT_INTEGRATION") != "1",
    reason="Dedicated isolated timeout tester required",
)
def test_abort_preserves_partial_results_and_rejects_later_runs():
    base = os.environ["HARNESS_TIMEOUT_URL"]
    assert base.startswith("http://127.0.0.1:")
    control = Path(os.environ["HARNESS_CONTROL_DIR"])
    (control / "pause-observed.json").unlink(missing_ok=True)
    (control / "fault.json").write_text(json.dumps({"pause_after_first_test": True}))
    try:
        ready = call(base, "tester", "POST", "/test/setup", 201, json={"target_url": TEAM2})
        failure = call(base, "tester", "POST", "/test/run", 500, json=ready)
        observed = json.loads((control / "pause-observed.json").read_text())
        assert observed["session_id"] == ready["session_id"] and observed["reset_request"] >= 2
    finally:
        (control / "fault.json").unlink(missing_ok=True)
    assert failure["source"] == "tester" and failure["message"]
    report = call(base, "tester", "GET", "/test/report", params=ready)
    check_suite(report)
    outcomes = [r["outcome"] for r in report["results"]]
    assert "pass" in outcomes and "skip" in outcomes
    assert any(r["outcome"] == "error" and r["source"] == "tester" for r in report["results"])
    assert report == call(base, "tester", "GET", "/test/report", params=ready)
    call(base, "tester", "POST", "/test/run", 409, json=ready)


@pytest.mark.skipif(
    os.getenv("HARNESS_CONTRACT_INTEGRATION") != "1",
    reason="Isolated system with stopped domain resources required",
)
def test_system_setup_remains_reachable_when_domain_database_is_unavailable():
    base = os.environ["HARNESS_UNAVAILABLE_SYSTEM_URL"]
    assert base.startswith("http://127.0.0.1:")
    prepared = {"session_id": "unavailable-" + uuid.uuid4().hex, "setup": {}}
    failure = call(base, "system", "POST", "/test/setup", 500, json=prepared)
    assert failure == {"message": "Could not initialize the session database.", "source": "system"}
    call(base, "system", "GET", "/test/report", 500, params={"session_id": prepared["session_id"]})
