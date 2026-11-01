"""Portable Phase 4 acceptance tests; only run against an approved disposable target.

Synthetic inputs are independent of the protected Team 6 fixtures. Original
Phase 3 assertions and conftest remain unchanged.
"""

import datetime as dt
import time

import pytest
from http_evidence import utc_now
from jsonschema import Draft202012Validator

STAGES = ("early_warning", "vulnerability_notification", "final_report")


def call(api, method, path, status=200, **kwargs):
    # Shared YAML omits negative responses for test-source, just as for clock.
    # Preserve it; record and validate those explicitly disclosed extensions.
    if (
        (path == "/test/vulnerability-source" and status >= 400)
        or (path.startswith("/vulnerabilities/") and status == 400)
        or (path.endswith("/submissions") and status == 409)
    ):
        started = time.monotonic()
        requested_at = utc_now()
        response = api.session.request(method, api.base_url + path, timeout=10, **kwargs)
        validation = "failed"
        try:
            Draft202012Validator(
                {"$ref": "urn:cra:contract#/components/schemas/Error"}, registry=api.registry
            ).validate(response.json())
            assert response.json()["error"]["message"].strip()
            validation = "passed"
        finally:
            api.evidence.record(
                dict(
                    test_id=api.test_id,
                    method=method,
                    path="/api/v1/vulnerabilities/{cveId}/affected-releases"
                    if path.startswith("/vulnerabilities/")
                    else "/api/v1" + path,
                    requested_at_utc=requested_at,
                    status=response.status_code,
                    documented=False,
                    schema_validation=validation,
                    seconds=time.monotonic() - started,
                ),
                response=response,
            )
    else:
        response = api.request(method, path, **kwargs)
    assert response.status_code == status, response.text
    return response.json()


def incident(api, classification="mandatory", **values):
    return call(
        api,
        "POST",
        "/incidents",
        201,
        json=dict(
            awareness_at="2026-11-01T00:00:00Z",
            classification=classification,
            rationale="  Engineer-confirmed exploitation; preserve rationale.\n",
            **values,
        ),
    )


def clock(api, now):
    return call(api, "PUT", "/test/clock", json={"now": now})


def submit(api, identifier, stage, timestamp):
    return call(
        api,
        "POST",
        f"/incidents/{identifier}/submissions",
        201,
        json=dict(stage=stage, submitted_at=timestamp),
    )


def seed(api):
    a = "pkg:generic/alpha@1"
    b = "pkg:generic/beta@2"
    c = "pkg:generic/gamma@4"
    patched = "pkg:generic/alpha@9"
    d = "pkg:generic/delta@5"
    inventories = [[a, b], [a, c], [patched, d]]
    releases = []
    for index, purls in enumerate(inventories):
        release = api.create(
            dict(
                product="Phase4 oracle",
                version=str(index),
                support_end_date=["2026-11-01", "2026-10-31", "2028-01-01"][index],
            )
        )
        components = [
            dict(
                type="library", name=p.split("/")[-1].split("@")[0], version=p.split("@")[1], purl=p
            )
            for p in purls
        ]
        # Exercise matching a nested component while retaining exact PURL identity.
        components[0]["components"] = [components.pop()]
        call(
            api,
            "PUT",
            f"/releases/{release['release_id']}/sbom",
            json=dict(bomFormat="CycloneDX", specVersion="1.6", version=1, components=components),
        )
        releases.append(release)
    vulnerable = [[a], [b], [patched], [c, d], [a, b, c]]
    records = [
        dict(cve_id=f"CVE-2026-{100 + i}", affected_purls=purls)
        for i, purls in enumerate(vulnerable)
    ]
    records.append(dict(cve_id="CVE-2026-999", affected_purls=["pkg:generic/absent@1"]))
    call(
        api,
        "PUT",
        "/test/vulnerability-source",
        json=dict(mode="available", records=records),
        headers={"X-User-Id": None},
    )
    return releases, inventories, vulnerable


@pytest.mark.parametrize("index", range(5))
def test_ac04_five_cves_exact_precision_recall_grouping_and_latency(api, index):
    releases, inventories, vulnerable = seed(api)
    started = time.monotonic()
    result = call(api, "GET", f"/vulnerabilities/CVE-2026-{100 + index}/affected-releases")
    assert time.monotonic() - started < 10
    assert result["cve_id"] == f"CVE-2026-{100 + index}"
    expected = {
        releases[i]["release_id"]: set(inv) & set(vulnerable[index])
        for i, inv in enumerate(inventories)
        if set(inv) & set(vulnerable[index])
    }
    actual = {
        r["release_id"]: {c["purl"] for c in r["matched_components"]}
        for group in ("supported", "unsupported")
        for r in result[group]
    }
    assert actual == expected  # Exact equality establishes both precision and recall.
    assert {r["release_id"] for r in result["unsupported"]} == (
        {releases[1]["release_id"]} & expected.keys()
    )
    assert len(actual) == sum(len(result[g]) for g in ("supported", "unsupported"))
    for group in ("supported", "unsupported"):
        for row in result[group]:
            original = next(r for r in releases if r["release_id"] == row["release_id"])
            assert all(row[k] == original[k] for k in ("product", "version", "support_end_date"))
            expected_components = {
                (p.split("/")[-1].split("@")[0], p.split("@")[1], p)
                for p in expected[row["release_id"]]
            }
            assert {
                (c["name"], c["version"], c["purl"]) for c in row["matched_components"]
            } == expected_components
            assert len(row["matched_components"]) == len(expected_components)


def test_ac04_support_group_uses_current_utc_clock(api):
    releases, _, _ = seed(api)
    clock(api, "2026-11-02T01:00:00+02:00")  # Still November 1 UTC.
    path = "/vulnerabilities/CVE-2026-100/affected-releases"
    assert len(call(api, "GET", path)["supported"]) == 1
    clock(api, "2026-11-02T00:00:00Z")
    result = call(api, "GET", path)
    assert result["supported"] == []
    assert {r["release_id"] for r in result["unsupported"]} == {
        r["release_id"] for r in releases[:2]
    }


def test_ac05_known_unaffected_unknown_and_outage_are_distinct(api):
    seed(api)
    path = "/vulnerabilities/{}/affected-releases"
    started = time.monotonic()
    result = call(api, "GET", path.format("CVE-2026-999"))
    assert result == dict(cve_id="CVE-2026-999", supported=[], unsupported=[])
    unknown = call(api, "GET", path.format("CVE-2026-123456"), 404)
    assert unknown["error"]["code"] == "CVE_UNKNOWN"
    call(api, "GET", path.format("invalid-cve"), 400)
    call(
        api,
        "PUT",
        "/test/vulnerability-source",
        400,
        data="{",
        headers={"Content-Type": "application/json"},
    )
    call(api, "PUT", "/test/vulnerability-source", json={"mode": "unreachable"})
    for cve in ("CVE-2026-100", "CVE-2026-123456"):
        failure = call(api, "GET", path.format(cve), 503)
        assert failure["error"]["code"] == "VULNERABILITY_SOURCE_UNREACHABLE"
    assert time.monotonic() - started < 15
    call(api, "PUT", "/test/vulnerability-source", json={"mode": "available"})
    call(api, "GET", path.format("CVE-2026-100"), 404)  # Mode-only PUT replaces with zero records.
    seed_records = [dict(cve_id="CVE-2026-100", affected_purls=["pkg:generic/alpha@1"])]
    call(
        api,
        "PUT",
        "/test/vulnerability-source",
        json={"mode": "available", "records": seed_records},
    )
    assert call(api, "GET", path.format("CVE-2026-100"))["supported"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"mode": "other"},
        {"mode": 1},
        {"mode": "available", "records": None},
        {"mode": "available", "records": {}},
        {"mode": "available", "records": [{"cve_id": "CVE-2026-100"}]},
        {"mode": "available", "records": [{"cve_id": 1, "affected_purls": []}]},
        {"mode": "available", "records": [{"cve_id": "CVE-2026-100", "affected_purls": [None]}]},
    ],
)
def test_ac05_invalid_source_configuration_preserves_previous_records(api, body):
    seed(api)
    call(api, "PUT", "/test/vulnerability-source", 400, json=body)
    assert call(api, "GET", "/vulnerabilities/CVE-2026-100/affected-releases")["supported"]


def test_ac05_explicit_empty_records_and_reset_restore_available_empty_source(api):
    seed(api)
    call(api, "PUT", "/test/vulnerability-source", json={"mode": "available", "records": []})
    call(api, "GET", "/vulnerabilities/CVE-2026-100/affected-releases", 404)
    seed_response = api.request("POST", "/test/reset")
    assert seed_response.status_code == 204
    call(api, "GET", "/vulnerabilities/CVE-2026-100/affected-releases", 404)


@pytest.mark.parametrize("classification", ["mandatory", "voluntary"])
def test_ac06_create_read_preserves_awareness_actor_classification_rationale(api, classification):
    result = incident(api, classification, cve_id="CVE-2026-100")
    fetched = call(api, "GET", f"/incidents/{result['incident_id']}")
    assert fetched == result
    assert result["awareness_at"] == "2026-11-01T00:00:00Z"
    assert result["created_by"] == "phase3-test-engineer"
    assert result["classification"] == classification
    assert result["rationale"] == "  Engineer-confirmed exploitation; preserve rationale.\n"
    assert result["cve_id"] == "CVE-2026-100"
    if classification == "voluntary":
        assert all(
            d == dict(deadline_at=None, submitted_at=None, status="not_applicable")
            for d in result["deadlines"].values()
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("classification", None),
        ("classification", "unknown"),
        ("classification", 1),
        ("rationale", None),
        ("rationale", ""),
        ("rationale", " \n"),
        ("rationale", 2),
        ("cve_id", 123),
    ],
)
def test_ac06_invalid_incident_fields(api, field, value):
    payload = dict(
        awareness_at="2026-11-01T00:00:00Z", classification="mandatory", rationale="reason"
    )
    payload[field] = value
    call(api, "POST", "/incidents", 400, json=payload)


@pytest.mark.parametrize("field", ["awareness_at", "classification", "rationale"])
def test_ac06_missing_incident_fields(api, field):
    payload = dict(
        awareness_at="2026-11-01T00:00:00Z", classification="mandatory", rationale="reason"
    )
    del payload[field]
    call(api, "POST", "/incidents", 400, json=payload)


def test_ac06_invalid_awareness_timestamp(api, invalid_clock_input):
    call(
        api,
        "POST",
        "/incidents",
        400,
        json=dict(awareness_at=invalid_clock_input, classification="mandatory", rationale="reason"),
    )


def test_ac06_aware_timestamp_normalized_to_utc(api, valid_clock_case):
    value, expected = valid_clock_case
    result = call(
        api,
        "POST",
        "/incidents",
        201,
        json=dict(awareness_at=value, classification="mandatory", rationale="reason"),
    )
    assert result["awareness_at"] == expected
    assert call(api, "GET", f"/incidents/{result['incident_id']}") == result


def test_ac07_exact_acceptance_sequence_and_independent_statuses(api):
    clock(api, "2026-11-01T00:00:00Z")
    result = incident(api)
    identifier = result["incident_id"]
    assert result["deadlines"]["early_warning"] == dict(
        deadline_at="2026-11-02T00:00:00Z", submitted_at=None, status="pending"
    )
    assert (
        result["deadlines"]["vulnerability_notification"]["deadline_at"] == "2026-11-04T00:00:00Z"
    )
    assert result["deadlines"]["final_report"] == dict(
        deadline_at=None, submitted_at=None, status="not_applicable"
    )
    result = submit(api, identifier, "early_warning", "2026-11-02T00:00:00Z")
    assert result["deadlines"]["early_warning"]["status"] == "met"
    clock(api, "2026-11-04T00:00:01Z")
    result = call(api, "GET", f"/incidents/{identifier}")
    assert result["deadlines"]["vulnerability_notification"]["status"] == "overdue"
    result = call(
        api, "PATCH", f"/incidents/{identifier}", json={"fix_available_at": "2026-11-05T00:00:00Z"}
    )
    assert result["deadlines"]["final_report"]["deadline_at"] == "2026-11-19T00:00:00Z"
    result = submit(api, identifier, "final_report", "2026-11-18T00:00:00Z")
    assert {s: result["deadlines"][s]["status"] for s in STAGES} == dict(
        early_warning="met", vulnerability_notification="overdue", final_report="met"
    )


@pytest.mark.parametrize(
    "stage,hours",
    [("early_warning", 24), ("vulnerability_notification", 72), ("final_report", 336)],
)
@pytest.mark.parametrize("delta,status", [(-1, "pending"), (0, "pending"), (1, "overdue")])
def test_ac07_unsubmitted_exact_clock_boundaries(api, stage, hours, delta, status):
    identifier = incident(api)["incident_id"]
    call(
        api, "PATCH", f"/incidents/{identifier}", json={"fix_available_at": "2026-11-01T00:00:00Z"}
    )
    base = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    clock(api, (base + dt.timedelta(hours=hours, seconds=delta)).isoformat())
    result = call(api, "GET", f"/incidents/{identifier}")
    assert result["deadlines"][stage]["status"] == status


@pytest.mark.parametrize(
    "stage,when",
    [
        ("early_warning", "2026-11-02T00:00:01Z"),
        ("vulnerability_notification", "2026-11-04T00:00:01Z"),
        ("final_report", "2026-11-15T00:00:01Z"),
    ],
)
def test_ac07_late_submissions_stay_overdue(api, stage, when):
    identifier = incident(api)["incident_id"]
    call(
        api, "PATCH", f"/incidents/{identifier}", json={"fix_available_at": "2026-11-01T00:00:00Z"}
    )
    result = submit(api, identifier, stage, when)
    assert result["deadlines"][stage]["status"] == "overdue"


@pytest.mark.parametrize(
    "aware,early,notification,fix,final",
    [
        (
            "2026-12-31T23:30:00-02:00",
            "2027-01-02T01:30:00Z",
            "2027-01-04T01:30:00Z",
            "2027-01-01T01:30:00Z",
            "2027-01-15T01:30:00Z",
        ),
        (
            "2028-02-28T12:00:00Z",
            "2028-02-29T12:00:00Z",
            "2028-03-02T12:00:00Z",
            "2028-02-28T12:00:00Z",
            "2028-03-13T12:00:00Z",
        ),
        (
            "2026-01-30T00:00:00Z",
            "2026-01-31T00:00:00Z",
            "2026-02-02T00:00:00Z",
            "2026-01-30T00:00:00Z",
            "2026-02-13T00:00:00Z",
        ),
    ],
)
def test_ac07_rollover_and_offsets(api, aware, early, notification, fix, final):
    result = call(
        api,
        "POST",
        "/incidents",
        201,
        json=dict(awareness_at=aware, classification="mandatory", rationale="rollover"),
    )
    result = call(
        api, "PATCH", f"/incidents/{result['incident_id']}", json={"fix_available_at": fix}
    )
    assert [result["deadlines"][s]["deadline_at"] for s in STAGES] == [early, notification, final]


@pytest.mark.parametrize("operation", ["patch", "submission"])
def test_ac07_invalid_mutation_timestamp(api, invalid_clock_input, operation):
    original = incident(api)
    identifier = original["incident_id"]
    if operation == "patch":
        call(
            api,
            "PATCH",
            f"/incidents/{identifier}",
            400,
            json={"fix_available_at": invalid_clock_input},
        )
    else:
        call(
            api,
            "POST",
            f"/incidents/{identifier}/submissions",
            400,
            json=dict(stage="early_warning", submitted_at=invalid_clock_input),
        )
    assert call(api, "GET", f"/incidents/{identifier}") == original


@pytest.mark.parametrize("stage", [None, "", "notification", "72h", 72])
def test_ac07_invalid_submission_stages(api, stage):
    original = incident(api)
    identifier = original["incident_id"]
    call(
        api,
        "POST",
        f"/incidents/{identifier}/submissions",
        400,
        json=dict(stage=stage, submitted_at="2026-11-02T00:00:00Z"),
    )
    assert call(api, "GET", f"/incidents/{identifier}") == original


def test_ac07_missing_fix_and_duplicate_submissions_are_rejected_without_overwrite(api):
    identifier = incident(api)["incident_id"]
    call(
        api,
        "POST",
        f"/incidents/{identifier}/submissions",
        400,
        json=dict(stage="final_report", submitted_at="2026-11-10T00:00:00Z"),
    )
    result = call(api, "GET", f"/incidents/{identifier}")
    assert result["deadlines"]["final_report"]["status"] == "not_applicable"
    result = call(
        api, "PATCH", f"/incidents/{identifier}", json={"fix_available_at": "2026-11-01T00:00:00Z"}
    )
    assert result["deadlines"]["final_report"]["status"] == "pending"
    result = submit(api, identifier, "final_report", "2026-11-10T00:00:00Z")
    assert result["deadlines"]["final_report"]["status"] == "met"
    submit(api, identifier, "early_warning", "2026-11-02T00:00:00Z")
    call(
        api,
        "POST",
        f"/incidents/{identifier}/submissions",
        409,
        json=dict(stage="early_warning", submitted_at="2026-11-03T00:00:00Z"),
    )
    result = call(api, "GET", f"/incidents/{identifier}")
    assert result["deadlines"]["early_warning"]["submitted_at"] == "2026-11-02T00:00:00Z"
    assert result["deadlines"]["early_warning"]["status"] == "met"


def test_ac07_unknown_incident_operations_and_missing_headers(api):
    for method, path, payload in [
        ("GET", "/incidents/unknown", None),
        ("PATCH", "/incidents/unknown", {"fix_available_at": "2026-11-01T00:00:00Z"}),
        (
            "POST",
            "/incidents/unknown/submissions",
            {"stage": "early_warning", "submitted_at": "2026-11-01T00:00:00Z"},
        ),
    ]:
        call(api, method, path, 404, **({"json": payload} if payload else {}))
    identifier = incident(api)["incident_id"]
    for method, path, payload in [
        (
            "POST",
            "/incidents",
            dict(awareness_at="2026-11-01T00:00:00Z", classification="mandatory", rationale="r"),
        ),
        ("PATCH", f"/incidents/{identifier}", {"fix_available_at": "2026-11-01T00:00:00Z"}),
        (
            "POST",
            f"/incidents/{identifier}/submissions",
            {"stage": "early_warning", "submitted_at": "2026-11-01T00:00:00Z"},
        ),
    ]:
        result = call(api, method, path, 400, json=payload, headers={"X-User-Id": None})
        assert result["error"]["code"] == "INVALID_REQUEST"


def test_ac07_overflow_is_rejected_without_corrupting_incident(api):
    call(
        api,
        "POST",
        "/incidents",
        400,
        json=dict(
            awareness_at="9999-12-31T00:00:00Z", classification="mandatory", rationale="overflow"
        ),
    )
    identifier = incident(api)["incident_id"]
    call(
        api,
        "PATCH",
        f"/incidents/{identifier}",
        400,
        json={"fix_available_at": "9999-12-31T00:00:00Z"},
    )
    assert call(api, "GET", f"/incidents/{identifier}")["fix_available_at"] is None


def test_ac07_reset_removes_incidents_and_submissions(api):
    identifier = incident(api)["incident_id"]
    submit(api, identifier, "early_warning", "2026-11-02T00:00:00Z")
    assert api.request("POST", "/test/reset").status_code == 204
    call(api, "GET", f"/incidents/{identifier}", 404)


@pytest.mark.parametrize(
    "input_purl,affected_purl,matched",
    [
        ("pkg:generic/alpha@1?arch=x#src/file", "pkg:generic/alpha@1", True),
        ("pkg:generic/alpha@1", "pkg:generic/alpha@1?arch=y#other", True),
        ("pkg:generic/alpha@1?arch=x", "pkg:generic/alpha@2?arch=x", False),
        (None, "pkg:generic/alpha@1", False),
    ],
)
def test_ac04_purl_identity_ignores_qualifiers_subpaths_but_not_versions(
    api, input_purl, affected_purl, matched
):
    release = api.create()
    component = dict(type="library", name="alpha", version="1")
    if input_purl is not None:
        component["purl"] = input_purl
    call(
        api,
        "PUT",
        f"/releases/{release['release_id']}/sbom",
        json=dict(bomFormat="CycloneDX", specVersion="1.6", version=1, components=[component]),
    )
    call(
        api,
        "PUT",
        "/test/vulnerability-source",
        json=dict(
            mode="available",
            records=[dict(cve_id="CVE-2026-10001", affected_purls=[affected_purl])],
        ),
    )
    result = call(api, "GET", "/vulnerabilities/CVE-2026-10001/affected-releases")
    assert result["unsupported"] == []
    assert {r["release_id"] for r in result["supported"]} == (
        {release["release_id"]} if matched else set()
    )
    if matched:
        assert result["supported"][0]["matched_components"] == [
            dict(name="alpha", version="1", purl=input_purl)
        ]


def test_ac05_replacement_and_reset_restore_available_empty_records(api):
    seed(api)
    call(
        api,
        "PUT",
        "/test/vulnerability-source",
        json=dict(mode="available", records=[dict(cve_id="CVE-2026-55555", affected_purls=[])]),
    )
    call(api, "GET", "/vulnerabilities/CVE-2026-100/affected-releases", 404)
    assert call(api, "GET", "/vulnerabilities/CVE-2026-55555/affected-releases")["supported"] == []
    call(api, "PUT", "/test/vulnerability-source", json=dict(mode="unreachable"))
    assert api.request("POST", "/test/reset").status_code == 204
    result = call(api, "GET", "/vulnerabilities/CVE-2026-55555/affected-releases", 404)
    assert result["error"]["code"] == "CVE_UNKNOWN"


@pytest.mark.parametrize("cve", ["abc", "CVE-26-1", "cve-2026-1", "CVE-2026-x", "", "CVE-2026-1\n"])
def test_ac06_malformed_incident_cve_is_invalid_request(api, cve):
    result = call(
        api,
        "POST",
        "/incidents",
        400,
        json=dict(
            awareness_at="2026-11-01T00:00:00Z",
            classification="mandatory",
            rationale="reason",
            cve_id=cve,
        ),
    )
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_ac06_incident_cve_needs_format_only_even_when_source_is_down(api):
    call(api, "PUT", "/test/vulnerability-source", json={"mode": "unreachable"})
    result = incident(api, cve_id="CVE-2026-99999")
    assert result["cve_id"] == "CVE-2026-99999"


@pytest.mark.parametrize("operation", ["patch", "submission"])
def test_ac07_timestamps_before_awareness_are_rejected_atomically(api, operation):
    original = incident(api)
    path = f"/incidents/{original['incident_id']}"
    earlier = "2026-11-01T00:59:59+01:00"
    if operation == "patch":
        call(api, "PATCH", path, 400, json={"fix_available_at": earlier})
    else:
        call(
            api,
            "POST",
            path + "/submissions",
            400,
            json=dict(stage="early_warning", submitted_at=earlier),
        )
    assert call(api, "GET", path) == original


@pytest.mark.parametrize("operation", ["patch", "submission"])
def test_ac07_aware_mutation_times_normalize_microseconds(api, valid_clock_case, operation):
    value, expected = valid_clock_case
    result = call(
        api,
        "POST",
        "/incidents",
        201,
        json=dict(
            awareness_at="2000-01-01T00:00:00Z",
            classification="mandatory",
            rationale="offset input",
        ),
    )
    path = f"/incidents/{result['incident_id']}"
    if operation == "patch":
        result = call(api, "PATCH", path, json={"fix_available_at": value})
        assert result["fix_available_at"] == expected
    else:
        result = submit(api, result["incident_id"], "early_warning", value)
        assert result["deadlines"]["early_warning"]["submitted_at"] == expected
        assert result["deadlines"]["early_warning"]["status"] == "overdue"
    assert call(api, "GET", path) == result


def test_ac07_future_fix_replacement_and_voluntary_stages(api):
    clock(api, "2026-11-01T00:00:00Z")
    original = incident(api)
    path = f"/incidents/{original['incident_id']}"
    call(api, "PATCH", path, json={"fix_available_at": "2026-12-01T00:00:00Z"})
    result = call(api, "PATCH", path, json={"fix_available_at": "2026-12-02T00:00:00Z"})
    assert result["fix_available_at"] == "2026-12-02T00:00:00Z"
    assert result["deadlines"]["final_report"]["deadline_at"] == "2026-12-16T00:00:00Z"
    assert (
        submit(api, original["incident_id"], "early_warning", "2026-12-01T00:00:00Z")["deadlines"][
            "early_warning"
        ]["status"]
        == "overdue"
    )
    voluntary = incident(api, "voluntary")
    path = f"/incidents/{voluntary['incident_id']}"
    result = call(api, "PATCH", path, json={"fix_available_at": "2026-12-02T00:00:00Z"})
    assert result["fix_available_at"] == "2026-12-02T00:00:00Z"
    assert all(d["status"] == "not_applicable" for d in result["deadlines"].values())
    for stage in STAGES:
        call(
            api,
            "POST",
            path + "/submissions",
            400,
            json=dict(stage=stage, submitted_at="2026-12-03T00:00:00Z"),
        )


def test_ac07_concurrent_duplicate_submissions_have_one_winner(api):
    from concurrent.futures import ThreadPoolExecutor

    import requests

    result = incident(api)
    path = f"/incidents/{result['incident_id']}/submissions"
    payload = dict(stage="early_warning", submitted_at="2026-11-02T00:00:00Z")

    def send(_):
        with requests.Session() as session:
            return session.post(
                api.base_url + path,
                json=payload,
                headers={"X-User-Id": "duplicate-regression"},
                timeout=10,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    for response in responses:
        schema = "Incident" if response.status_code == 201 else "Error"
        Draft202012Validator(
            {"$ref": "urn:cra:contract#/components/schemas/" + schema}, registry=api.registry
        ).validate(response.json())
        api.evidence.record(
            dict(
                test_id=api.test_id,
                method="POST",
                path="/api/v1/incidents/{incidentId}/submissions",
                requested_at_utc=utc_now(),
                status=response.status_code,
                documented=response.status_code == 201,
                schema_validation="passed",
            ),
            response=response,
        )
    stored = call(api, "GET", f"/incidents/{result['incident_id']}")
    assert stored["deadlines"]["early_warning"]["submitted_at"] == payload["submitted_at"]
