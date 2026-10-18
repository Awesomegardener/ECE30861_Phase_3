"""HTTP tests run only when reset permission is explicitly provided."""

import json
import os
import re
import time
from pathlib import Path

import pytest
import requests
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:18080"))
    parser.addoption(
        "--allow-reset",
        action="store_true",
        help="Allow destructive reset on the selected coordinated target",
    )


@pytest.fixture(scope="session")
def release_cases():
    return json.loads((ROOT / "fixtures/releases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def shared_sbom():
    return json.loads((ROOT / "fixtures/sbom_25_components.json").read_text(encoding="utf-8"))


class Api:
    def __init__(self, base_url, spec):
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/api/v1"):
            self.base_url += "/api/v1"
        self.session = requests.Session()
        self.session.headers["X-User-Id"] = "phase3-test-engineer"
        self.spec = spec
        self.registry = Registry().with_resource(
            "urn:cra:contract", DRAFT202012.create_resource(spec)
        )
        self.observations = []

    def request(self, method, path, *, undocumented=False, **kwargs):
        start = time.monotonic()
        response = self.session.request(method, self.base_url + path, timeout=10, **kwargs)
        route = next(
            route
            for route in self.spec["paths"]
            if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", route), "/api/v1" + path)
        )
        operation = self.spec["paths"][route][method.lower()]
        code = str(response.status_code)
        self.observations.append(
            {
                "method": method,
                "path": route,
                "status": response.status_code,
                "seconds": round(time.monotonic() - start, 4),
                "documented": code in operation["responses"],
            }
        )
        if code not in operation["responses"]:
            assert undocumented, (method, path, response.status_code, response.text)
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
        return response

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
def client(request):
    if not request.config.getoption("--allow-reset"):
        pytest.fail(
            "HTTP tests reset data. Select an isolated/coordinated --base-url and explicitly pass --allow-reset."
        )
    spec = yaml.safe_load((ROOT / "docs/openapi.yaml").read_text(encoding="utf-8"))
    api = Api(request.config.getoption("--base-url"), spec)
    yield api
    api.session.close()
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "operation-observations.json").write_text(
        json.dumps(api.observations, indent=2), encoding="utf-8"
    )


@pytest.fixture
def api(client, release_cases):
    response = client.request("POST", "/test/reset")
    assert response.status_code == 204
    response = client.request("PUT", "/test/clock", json={"now": release_cases["reference_clock"]})
    assert response.status_code == 200
    assert response.json()["now"] == release_cases["reference_clock"]
    return client
