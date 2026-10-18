"""HTTP tests run only when reset permission is explicitly provided."""

import json
import os
import re
import time
from pathlib import Path

import pytest
import requests
import yaml
from http_evidence import HttpEvidence, utc_now
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(
    params=[
        None,
        True,
        1793491200,
        1793491200.5,
        [],
        {},
        "",
        "invalid",
        "1793491200",
        "1793491200000",
        "-1",
        "2026-11-01",
        "2026-11-01T12:00:00",
        "2026-11-01 12:00:00Z",
        "2026-11-01_12:00:00Z",
        "2026-11-01T12:00Z",
        "2026-11-01T12:00:00+0200",
        "2026-11-01T12:00:00+02",
        "2026-11-01T12:00:00+24:00",
        "2026-11-01T12:00:00+00:60",
        "2026-11-01T24:00:00Z",
        "2026-11-01T12:60:00Z",
        "2026-11-01T12:00:61Z",
        "2026-02-30T12:00:00Z",
        "2026-13-01T12:00:00Z",
        "2026-11-01T12:00:00,5Z",
        "2026-11-01T12:00:00.Z",
        " 2026-11-01T12:00:00Z",
        "2026-11-01T12:00:00Z\n",
    ]
)
def invalid_clock_input(request):
    return request.param


@pytest.fixture(
    params=[
        ("2026-11-01T23:59:59Z", "2026-11-01T23:59:59Z"),
        ("2026-11-01t23:59:59z", "2026-11-01T23:59:59Z"),
        ("2026-11-01T23:59:59+00:00", "2026-11-01T23:59:59Z"),
        ("2026-11-01T23:59:59-00:00", "2026-11-01T23:59:59Z"),
        ("2026-11-02T01:00:00+02:00", "2026-11-01T23:00:00Z"),
        ("2026-11-01T20:30:00-05:30", "2026-11-02T02:00:00Z"),
        ("2026-11-02T01:15:00+05:45", "2026-11-01T19:30:00Z"),
        ("2026-11-01T12:00:00+23:59", "2026-10-31T12:01:00Z"),
        ("2026-11-01T12:00:00-23:59", "2026-11-02T11:59:00Z"),
        ("2026-11-01T23:59:59.1Z", "2026-11-01T23:59:59.100000Z"),
        ("2026-11-01T23:59:59.123456+02:00", "2026-11-01T21:59:59.123456Z"),
        ("2026-11-01T23:59:59.123456789Z", "2026-11-01T23:59:59.123456Z"),
        ("2028-02-29T23:59:59Z", "2028-02-29T23:59:59Z"),
    ],
    ids=lambda case: case[0],
)
def valid_clock_case(request):
    return request.param


@pytest.fixture(scope="session")
def contract():
    return yaml.safe_load((ROOT / "docs/openapi.yaml").read_text(encoding="utf-8"))


def pytest_addoption(parser):
    parser.addoption("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:18080"))
    parser.addoption(
        "--allow-reset",
        action="store_true",
        help="Allow destructive reset on the selected coordinated target",
    )
    parser.addoption("--evidence-dir", type=Path, default=ROOT / "artifacts")
    parser.addoption(
        "--capture-http-bodies",
        action="store_true",
        help="Save redacted, bounded request/response bodies from synthetic test data",
    )
    parser.addoption("--tested-commit", default=os.getenv("TESTED_COMMIT_SHA"))
    parser.addoption("--evidence-body-limit", type=int, default=65536)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    path = getattr(config, "http_evidence_path", None)
    if path:
        terminalreporter.write_line(f"HTTP report evidence: {path}")


@pytest.fixture(scope="session")
def release_cases():
    return json.loads((ROOT / "fixtures/releases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def shared_sbom():
    return json.loads((ROOT / "fixtures/sbom_25_components.json").read_text(encoding="utf-8"))


@pytest.fixture(params=["1.4", "1.5", "1.6"])
def sbom_spec_version(request):
    return request.param


@pytest.fixture
def nested_sbom(sbom_spec_version):
    """Synthetic regression input, separate from the protected Team 6 fixtures."""

    def leaf(reference):
        return {
            "type": "library",
            "bom-ref": reference,
            "name": "shared-leaf",
            "version": "2.0",
            "purl": "pkg:generic/shared-leaf@2.0",
        }

    tool = {
        "type": "application",
        "name": "tool-only",
        "version": "99",
        "components": [{"type": "library", "name": "tool-child", "version": "99"}],
    }
    return {
        "bomFormat": "CycloneDX",
        "specVersion": sbom_spec_version,
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "metadata-root",
                "version": "99",
                "components": [{"type": "library", "name": "metadata-child", "version": "99"}],
            },
            "tools": (
                [{"vendor": "Regression tests", "name": "tool-only", "version": "99"}]
                if sbom_spec_version == "1.4"
                else {"components": [tool]}
            ),
        },
        "components": [
            {
                "type": "application",
                "name": "assembly-a",
                "version": "1.0",
                "components": [
                    leaf("child-a"),
                    {
                        "type": "library",
                        "name": "middle",
                        "version": "3.0",
                        "components": [
                            {"type": "library", "name": "deep-leaf", "version": "4.0"},
                            leaf("deep-copy"),
                        ],
                    },
                ],
            },
            leaf("root-copy"),
            {
                "type": "library",
                "name": "assembly-b",
                "version": "5.0",
                "components": [leaf("child-b")],
            },
        ],
    }


@pytest.fixture
def nested_inventory():
    # Independent flat oracle: four unique assemblies/leaves plus four occurrences
    # of the same name/version/purl. The shared fixture itself is never edited.
    return [
        {"name": "assembly-a", "version": "1.0"},
        {"name": "middle", "version": "3.0"},
        {"name": "deep-leaf", "version": "4.0"},
        {"name": "assembly-b", "version": "5.0"},
        *[
            {"name": "shared-leaf", "version": "2.0", "purl": "pkg:generic/shared-leaf@2.0"}
            for _ in range(4)
        ],
    ]


class Api:
    def __init__(self, base_url, spec, evidence):
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/api/v1"):
            self.base_url += "/api/v1"
        self.session = requests.Session()
        self.session.headers["X-User-Id"] = "phase3-test-engineer"
        self.spec = spec
        self.registry = Registry().with_resource(
            "urn:cra:contract", DRAFT202012.create_resource(spec)
        )
        self.evidence = evidence
        self.test_id = None

    def request(self, method, path, *, undocumented=False, session=None, **kwargs):
        start = time.monotonic()
        requested_at = utc_now()
        route = next(
            route
            for route in self.spec["paths"]
            if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", route), "/api/v1" + path)
        )
        operation = self.spec["paths"][route][method.lower()]
        observation = {
            "test_id": self.test_id,
            "method": method.upper(),
            "path": route,
            "requested_at_utc": requested_at,
            "status": None,
            "documented": None,
            "schema_validation": "not_checked",
        }
        url = self.base_url + path
        try:
            response = (session or self.session).request(method, url, timeout=10, **kwargs)
        except requests.RequestException as exc:
            observation.update(
                request_error=type(exc).__name__,
                failed_at_utc=utc_now(),
                seconds=round(time.monotonic() - start, 4),
            )
            self.evidence.record(observation, prepared=exc.request, url=url)
            raise
        code = str(response.status_code)
        observation.update(
            status=response.status_code,
            documented=code in operation["responses"],
            received_at_utc=utc_now(),
            seconds=round(time.monotonic() - start, 4),
        )
        try:
            self.validate_response(response, route, method, operation, code, undocumented)
            observation["schema_validation"] = "passed"
        except Exception as exc:
            observation.update(schema_validation="failed", validation_error=type(exc).__name__)
            raise
        finally:
            self.evidence.record(observation, response=response)
        return response

    def validate_response(self, response, route, method, operation, code, undocumented):
        if code not in operation["responses"]:
            assert undocumented, (method, route, response.status_code, response.text)
            assert route == "/api/v1/test/clock" and code == "400"
            Draft202012Validator(
                {"$ref": "urn:cra:contract#/components/schemas/Error"}, registry=self.registry
            ).validate(response.json())
        elif response.status_code == 204:
            assert response.content == b""
        elif "content" in operation["responses"][code]:
            assert response.headers["Content-Type"].startswith("application/json")
            pointer = route.replace("~", "~0").replace("/", "~1")
            ref = f"urn:cra:contract#/paths/{pointer}/{method.lower()}/responses/{code}/content/application~1json/schema"
            Draft202012Validator(
                {"$ref": ref}, registry=self.registry, format_checker=FormatChecker()
            ).validate(response.json())
        if response.status_code >= 400:
            # Exact codes are asserted at explicitly agreed call sites, not
            # globally: another implementation may use different unmapped codes.
            assert response.json()["error"]["message"].strip(), (
                "Error message must explain the failure"
            )

    def create(self, payload=None):
        payload = payload or {
            "product": "TestRouter",
            "version": "1.0",
            "support_end_date": "2027-01-01",
        }
        response = self.request("POST", "/releases", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    def components(self, release_id):
        response = self.request("GET", f"/releases/{release_id}/components")
        assert response.status_code == 200, response.text
        return response.json()["components"]


@pytest.fixture(scope="session")
def client(request, contract):
    if not request.config.getoption("--allow-reset"):
        pytest.fail(
            "HTTP tests reset data. Select an isolated/coordinated --base-url and explicitly pass --allow-reset."
        )
    limit = request.config.getoption("--evidence-body-limit")
    if limit < 1:
        raise pytest.UsageError("--evidence-body-limit must be positive")
    commit = request.config.getoption("--tested-commit")
    if commit is not None and not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit):
        raise pytest.UsageError("--tested-commit must be the target's full Git SHA")
    base_url = request.config.getoption("--base-url").rstrip("/")
    if not base_url.endswith("/api/v1"):
        base_url += "/api/v1"
    evidence = HttpEvidence(
        ROOT,
        request.config.getoption("--evidence-dir"),
        base_url,
        capture_bodies=request.config.getoption("--capture-http-bodies"),
        body_limit=limit,
        tested_commit=commit,
    )
    api = Api(base_url, contract, evidence)
    try:
        yield api
    finally:
        api.session.close()
        request.config.http_evidence_path = evidence.write()


@pytest.fixture
def api(client, release_cases, request):
    client.test_id = request.node.nodeid
    response = client.request("POST", "/test/reset")
    assert response.status_code == 204
    response = client.request("PUT", "/test/clock", json={"now": release_cases["reference_clock"]})
    assert response.status_code == 200
    assert response.json()["now"] == release_cases["reference_clock"]
    return client
