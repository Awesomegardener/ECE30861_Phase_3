"""REQ-01/02 acceptance and regression tests against the shared HTTP contract."""

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
import requests


def inventory(components):
    return Counter((c["name"], c["version"], c.get("purl")) for c in components)


def test_ac01_shared_release_cases(api, release_cases):
    for case in release_cases["ac01"]["cases"]:
        response = api.request("POST", "/releases", json=case["request"])
        expected = case["expected"]
        assert response.status_code == expected["http_status"]
        if response.status_code == 201:
            release = response.json()
            assert release["support_status"] == expected["support_status"]
            fetched = api.request("GET", f"/releases/{release['release_id']}")
            assert fetched.status_code == 200 and fetched.json() == release
        else:
            assert response.json()["error"]["code"] == expected["error_code"]
            assert "support_end_date" in response.json()["error"]["message"]
            api.create({**case["request"], "support_end_date": "2027-01-01"})


@pytest.mark.parametrize(
    "now,status",
    [
        ("2026-11-01T00:00:00Z", "supported"),
        ("2026-11-01T23:59:59.999999Z", "supported"),
        ("2026-11-02T00:00:00Z", "unsupported"),
    ],
)
def test_ac01_support_boundary(api, now, status):
    release = api.create(
        {"product": "BoundaryRouter", "version": "1", "support_end_date": "2026-11-01"}
    )
    assert api.request("PUT", "/test/clock", json={"now": now}).status_code == 200
    response = api.request("GET", f"/releases/{release['release_id']}")
    assert response.json()["support_status"] == status


@pytest.mark.parametrize(
    "field,value",
    [
        ("product", 1),
        ("product", True),
        ("product", None),
        ("product", {}),
        ("version", 1),
        ("version", False),
        ("version", None),
        ("version", []),
        ("support_end_date", 1793491200),
        ("support_end_date", "2026-11-01T00:00:00Z"),
        ("support_end_date", "2026-02-30"),
        ("support_end_date", None),
    ],
)
def test_release_invalid_types_save_nothing(api, field, value):
    valid = {"product": "InvalidRouter", "version": "1", "support_end_date": "2027-01-01"}
    response = api.request("POST", "/releases", json={**valid, field: value})
    assert response.status_code == 400
    assert field in response.json()["error"]["message"]
    api.create(valid)


@pytest.mark.parametrize("missing", ["product", "version"])
def test_release_missing_required_fields(api, missing):
    valid = {"product": "MissingRouter", "version": "1", "support_end_date": "2027-01-01"}
    response = api.request(
        "POST", "/releases", json={k: v for k, v in valid.items() if k != missing}
    )
    assert response.status_code == 400
    assert missing in response.json()["error"]["message"]
    api.create(valid)


def test_release_malformed_json(api):
    response = api.request(
        "POST", "/releases", data="{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_release_duplicate_and_long_strings(api):
    payload = {"product": "p" * 300, "version": "v" * 120, "support_end_date": "2027-01-01"}
    api.create(payload)
    assert api.request("POST", "/releases", json=payload).status_code == 409


@pytest.mark.parametrize("header", [None, ""])
def test_release_requires_nonempty_user(api, header):
    response = api.request(
        "POST",
        "/releases",
        headers={"X-User-Id": header},
        json={"product": "HeaderRouter", "version": "1", "support_end_date": "2027-01-01"},
    )
    assert response.status_code == 400
    api.create({"product": "HeaderRouter", "version": "1", "support_end_date": "2027-01-01"})


@pytest.mark.parametrize("suffix", ["", "/components"])
def test_unknown_release(api, suffix):
    assert api.request("GET", "/releases/not-registered" + suffix).status_code == 404


def test_ac02_shared_25_components_are_isolated(api, release_cases, shared_sbom):
    cases = release_cases["ac02"]["releases"]
    releases = [api.create(case["request"]) for case in cases]
    assert api.components(releases[0]["release_id"]) == []
    response = api.request("PUT", f"/releases/{releases[0]['release_id']}/sbom", json=shared_sbom)
    assert response.status_code == cases[0]["expected"]["sbom_http_status"]
    assert response.json() == {"release_id": releases[0]["release_id"], "component_count": 25}
    components = api.components(releases[0]["release_id"])
    assert len(components) == 25
    assert inventory(components) == inventory(shared_sbom["components"])
    assert api.components(releases[1]["release_id"]) == []


def invalid_payload(shared_sbom, kind):
    document = deepcopy(shared_sbom)
    if kind == "malformed":
        return {"data": "{", "headers": {"Content-Type": "application/json"}}, "JSON"
    if kind == "plaintext":
        return {"data": "This is not JSON", "headers": {"Content-Type": "text/plain"}}, "JSON"
    if kind.startswith("root_"):
        value = {"root_null": None, "root_array": [], "root_number": 1}[kind]
        return {
            "data": json.dumps(value),
            "headers": {"Content-Type": "application/json"},
        }, "object"
    if kind in {"bomFormat", "specVersion"}:
        del document[kind]
        reason = kind
    elif kind == "missing_type":
        del document["components"][-1]["type"]
        reason = "type"
    elif kind == "missing_name":
        del document["components"][-1]["name"]
        reason = "name"
    elif kind == "wrong_version_type":
        document["components"][-1]["version"] = 1
        reason = "version"
    elif kind == "wrong_components_type":
        document["components"] = {}
        reason = "components"
    elif kind == "null_component":
        document["components"][-1] = None
        reason = "components"
    elif kind == "invalid_nested_child":
        document["components"][-1]["components"] = [{"name": "nested-invalid", "version": "1"}]
        reason = "type"
    else:
        raise AssertionError(kind)
    return {"json": document}, reason


INVALID_SBOMS = [
    "malformed",
    "plaintext",
    "root_null",
    "root_array",
    "root_number",
    "bomFormat",
    "specVersion",
    "missing_type",
    "missing_name",
    "wrong_version_type",
    "wrong_components_type",
    "null_component",
    "invalid_nested_child",
]


@pytest.mark.parametrize("kind", INVALID_SBOMS)
@pytest.mark.parametrize("existing", [False, True], ids=["empty", "preserve-existing"])
def test_ac03_invalid_sbom_never_changes_inventory(api, shared_sbom, kind, existing):
    release = api.create()
    release_id = release["release_id"]
    path = f"/releases/{release_id}/sbom"
    if existing:
        assert api.request("PUT", path, json=shared_sbom).status_code == 200
    before = inventory(api.components(release_id))
    kwargs, reason = invalid_payload(shared_sbom, kind)
    response = api.request("PUT", path, **kwargs)
    assert response.status_code == 400
    assert reason.lower() in response.json()["error"]["message"].lower()
    assert inventory(api.components(release_id)) == before


def test_sbom_requires_json_media_type(api, shared_sbom):
    release = api.create()
    response = api.request(
        "PUT",
        f"/releases/{release['release_id']}/sbom",
        json=shared_sbom,
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 400
    assert "application/json" in response.json()["error"]["message"]
    assert api.components(release["release_id"]) == []


def test_ac03_unknown_release_stores_nothing(api, shared_sbom):
    release = api.create()
    response = api.request("PUT", "/releases/not-registered/sbom", json=shared_sbom)
    assert response.status_code == 404
    assert "not found" in response.json()["error"]["message"].lower()
    assert api.components(release["release_id"]) == []


@pytest.mark.parametrize("header", [None, ""])
def test_sbom_requires_nonempty_user(api, shared_sbom, header):
    release = api.create()
    response = api.request(
        "PUT",
        f"/releases/{release['release_id']}/sbom",
        json=shared_sbom,
        headers={"X-User-Id": header},
    )
    assert response.status_code == 400
    assert api.components(release["release_id"]) == []


def test_sbom_replacement_is_idempotent(api, shared_sbom):
    release = api.create()
    path = f"/releases/{release['release_id']}/sbom"
    assert api.request("PUT", path, json=shared_sbom).status_code == 200
    replacement = deepcopy(shared_sbom)
    replacement["components"] = replacement["components"][:2]
    for _ in range(2):
        response = api.request("PUT", path, json=replacement)
        assert response.json()["component_count"] == 2
        assert inventory(api.components(release["release_id"])) == inventory(
            replacement["components"]
        )


def test_concurrent_replacements_do_not_merge(api, shared_sbom):
    release = api.create()
    url = api.base_url + f"/releases/{release['release_id']}/sbom"
    payloads = [deepcopy(shared_sbom), deepcopy(shared_sbom)]
    payloads[0]["components"] = payloads[0]["components"][:10]
    payloads[1]["components"] = payloads[1]["components"][10:]

    def upload(document):
        return requests.put(
            url, json=document, headers={"X-User-Id": "concurrent-test"}, timeout=10
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(upload, payloads))
    assert all(response.status_code == 200 for response in responses)
    result = inventory(api.components(release["release_id"]))
    assert result in [inventory(document["components"]) for document in payloads]


@pytest.mark.parametrize("value", [None, 1793491200, "invalid", "2026-11-01T12:00:00"])
def test_invalid_clock_preserves_reference(api, value):
    response = api.request("PUT", "/test/clock", json={"now": value}, undocumented=True)
    assert response.status_code == 400
    release = api.create(
        {"product": "ClockRouter", "version": "1", "support_end_date": "2026-10-31"}
    )
    assert release["support_status"] == "unsupported"


def test_clock_offset_uses_utc_date(api):
    response = api.request("PUT", "/test/clock", json={"now": "2026-11-02T01:00:00+02:00"})
    assert response.json()["now"] == "2026-11-01T23:00:00Z"
    release = api.create({"product": "UtcRouter", "version": "1", "support_end_date": "2026-11-01"})
    assert release["support_status"] == "supported"


def test_reset_is_repeatable_and_clears_inventory(api, shared_sbom):
    release = api.create()
    assert (
        api.request("PUT", f"/releases/{release['release_id']}/sbom", json=shared_sbom).status_code
        == 200
    )
    for _ in range(2):
        assert api.request("POST", "/test/reset", headers={"X-User-Id": None}).status_code == 204
    assert api.request("GET", f"/releases/{release['release_id']}").status_code == 404
    assert api.request("GET", f"/releases/{release['release_id']}/components").status_code == 404
    api.create()
