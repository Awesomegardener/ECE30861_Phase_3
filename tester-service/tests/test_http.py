"""Real HTTP setup/run/report tests, only for the isolated Docker stack.

Set HARNESS_INTEGRATION=1 and HARNESS_SYSTEM_URL/HARNESS_TESTER_URL.
Never point these destructive tests at a public or retained database.
"""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.getenv("HARNESS_INTEGRATION") != "1", reason="Isolated Docker stack required"
)


@pytest.fixture(scope="module")
def urls():
    system = os.environ["HARNESS_SYSTEM_URL"]
    tester = os.environ["HARNESS_TESTER_URL"]
    assert system.startswith("http://127.0.0.1:") and tester.startswith("http://127.0.0.1:")
    return {"system": system, "tester": tester}


def request(base, method, path, expected=200, **kwargs):
    response = requests.request(method, base + path, timeout=660, **kwargs)
    assert response.status_code == expected, response.text
    body = response.json()
    specifications = [ROOT / "docs/autograder-openapi.yaml"]
    reference = os.getenv("TEAM6_AUTOGRADER_SPEC")
    if reference:
        specifications.append(Path(reference))
    route = path.split("?")[0]
    for file in specifications:
        spec = yaml.safe_load(file.read_text(encoding="utf-8"))
        operation = spec["paths"][route][method.lower()]
        # 503 and setup 409 are explicitly documented Team 2 safety extensions.
        if str(expected) not in operation["responses"]:
            continue
        registry = Registry().with_resource("urn:adapter", DRAFT202012.create_resource(spec))
        pointer = route.replace("/", "~1")
        ref = f"urn:adapter#/paths/{pointer}/{method.lower()}/responses/{expected}"
        resolved = registry.resolver().lookup(ref).contents
        if "$ref" in resolved:
            ref = "urn:adapter" + resolved["$ref"]
        Draft202012Validator(
            {"$ref": ref + "/content/application~1json/schema"},
            registry=registry,
            format_checker=FormatChecker(),
        ).validate(body)
    return body


def setup(base, **values):
    return request(base, "POST", "/test/setup", json=values or {})["session_id"]


@pytest.mark.parametrize("role", ["system", "tester"])
def test_discovery_and_real_suite(urls, role):
    base = urls[role]
    discovery = request(base, "GET", "/test")
    assert discovery["role"] == role
    assert discovery["reset_ready"] is (role == "system")
    identifier = setup(base)
    before = request(base, "GET", f"/test/report?session_id={identifier}")
    assert before["status"] == "ready" and before["checks"] == []
    outcome = request(base, "POST", "/test/run", json={"session_id": identifier})
    assert outcome["result"] == "pass", outcome
    assert outcome["summary"]["passed"] == outcome["summary"]["total"] == 157
    report = request(base, "GET", f"/test/report?session_id={identifier}")
    assert report["result"] == "pass" and len(report["checks"]) == 157
    assert all(check["passed"] for check in report["checks"])
    assert report["duration_ms"] > 0 and report["started_at"] and report["finished_at"]
    assert report["evidence"]["exchanges"]
    assert request(base, "POST", "/test/run", json={"session_id": identifier}) == outcome
    evidence = Path(os.getenv("HARNESS_EVIDENCE_DIR", ROOT / "artifacts/autograder"))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{role}-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.parametrize("role", ["system", "tester"])
def test_invalid_requests_and_sessions(urls, role):
    base = urls[role]
    for path, method in [("/test/run", "POST"), ("/test/report?session_id=does-not-exist", "GET")]:
        body = request(
            base,
            method,
            path,
            expected=404,
            **({"json": {"session_id": "does-not-exist"}} if method == "POST" else {}),
        )
        assert body["error"]["code"] == "SESSION_NOT_FOUND"
    for value in [
        None,
        "http://169.254.169.254",
        "https://example.com",
        "http://api:8080@evil.example",
    ]:
        assert (
            request(base, "POST", "/test/setup", expected=400, json={"target_base_url": value})[
                "error"
            ]["code"]
            == "INVALID_TARGET"
        )
    for body in ["{", "[]", "null"]:
        request(base, "POST", "/test/setup", expected=400, data=body)
    request(
        base, "POST", "/test/setup?session_id=first", expected=400, json={"session_id": "second"}
    )
    identifier = "query-" + uuid.uuid4().hex
    result = request(base, "POST", f"/test/setup?session_id={identifier}")
    assert result["session_id"] == identifier
    request(base, "POST", "/test/setup", expected=409, json={"session_id": identifier})


def test_invalid_clock_does_not_reset_database(urls):
    base = urls["system"]
    payload = dict(
        product="Must survive invalid setup",
        version=str(uuid.uuid4()),
        support_end_date="2099-01-01",
    )
    release = requests.post(
        base + "/api/v1/releases",
        json=payload,
        headers={"X-User-Id": "adapter-regression"},
        timeout=10,
    )
    assert release.status_code == 201
    request(base, "POST", "/test/setup", expected=400, json={"now": "2026-02-30T00:00:00Z"})
    assert (
        requests.get(
            base + "/api/v1/releases/" + release.json()["release_id"], timeout=10
        ).status_code
        == 200
    )
    setup(base, now="2026-11-02T01:00:00+02:00")
    payload["version"] = str(uuid.uuid4())
    payload["support_end_date"] = "2026-11-01"
    result = requests.post(
        base + "/api/v1/releases",
        json=payload,
        headers={"X-User-Id": "adapter-regression"},
        timeout=10,
    )
    assert result.status_code == 201 and result.json()["support_status"] == "supported"


def test_real_failing_target_reports_failures(urls):
    identifier = setup(urls["tester"], target_base_url="http://broken:8080")
    outcome = request(urls["tester"], "POST", "/test/run", json={"session_id": identifier})
    report = request(urls["tester"], "GET", f"/test/report?session_id={identifier}")
    assert outcome["result"] == report["result"] == "fail"
    assert report["summary"]["failed"] > 0 and report["summary"]["errors"] == 0
    assert any(not check["passed"] and check["actual"] for check in report["checks"])
    assert len(report["checks"]) == 157
    evidence = Path(os.getenv("HARNESS_EVIDENCE_DIR", ROOT / "artifacts/autograder"))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "failing-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_concurrent_adapters_cannot_reset_or_run_during_suite(urls):
    identifier = setup(urls["tester"])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            request, urls["tester"], "POST", "/test/run", json={"session_id": identifier}
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            report = request(urls["tester"], "GET", f"/test/report?session_id={identifier}")
            if report.get("running"):
                break
            time.sleep(0.05)
        assert report["running"] and report["status"] == "ready"
        for role in ("system", "tester"):
            request(urls[role], "POST", "/test/setup", expected=409)
            request(urls[role], "POST", "/test/run", expected=409)
        assert future.result()["result"] == "pass"


def test_real_redirect_cannot_forward_a_reset_to_an_unapproved_system(urls):
    sentinel = os.getenv("HARNESS_SENTINEL_URL", "http://127.0.0.1:18092")
    assert sentinel.startswith("http://127.0.0.1:")
    before = requests.get(sentinel + "/count", timeout=5).json()["destructive_requests"]
    assert before == 0
    identifier = setup(urls["tester"], target_base_url="http://redirect:8080")
    outcome = request(urls["tester"], "POST", "/test/run", json={"session_id": identifier})
    report = request(urls["tester"], "GET", f"/test/report?session_id={identifier}")
    assert outcome["result"] == report["result"] == "error"
    assert report["summary"]["passed"] == 0 and report["summary"]["errors"] == 157
    assert requests.get(sentinel + "/count", timeout=5).json()["destructive_requests"] == before
