"""Portable Phase 5 acceptance tests (AC-08, AC-09) for an approved disposable target.

Oracles come from the pod Phase 5 answers (Q1-Q5) and the shared contract 1.1.0:
the per-stage field lists in CRA Art. 14(2), the agreed "missing" rule, the agreed
check order, and the seven audit actions. Expected values are written out here
rather than derived from the service's own responses.
"""

import json

import pytest
import requests

STAGE_FIELDS = {
    "early_warning": {"member_states": ["DE", "FR"]},
    "vulnerability_notification": {
        "product_information": "ExampleRouter 2.4.1",
        "exploit_nature": "Remote exploitation of vulnerable library",
        "vulnerability_nature": "Input validation vulnerability",
        "corrective_measures_taken": "Patched library version prepared",
        "user_mitigations": "Disable affected feature until update",
        "sensitivity": "TLP:AMBER",
    },
    "final_report": {
        "vulnerability_description": "Heap overflow in parser",
        "severity": "high",
        "impact": "Remote code execution on exposed devices",
        "corrective_measure_details": "Firmware 2.4.2 replaces the parser",
        "malicious_actor_information": "Unknown actor",
    },
}
REQUIRED = {
    "early_warning": ["member_states"],
    "vulnerability_notification": [
        "product_information",
        "exploit_nature",
        "vulnerability_nature",
        "corrective_measures_taken",
        "user_mitigations",
    ],
    "final_report": [
        "vulnerability_description",
        "severity",
        "impact",
        "corrective_measure_details",
    ],
}
CLOCK = "2026-11-01T23:59:59Z"


def call(api, method, path, status, **kwargs):
    response = api.request(method, path, **kwargs)
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def incident(api, classification="mandatory", user=None):
    headers = {"X-User-Id": user} if user else {}
    return call(
        api,
        "POST",
        "/incidents",
        201,
        headers=headers,
        json={
            "awareness_at": "2026-11-01T00:00:00Z",
            "classification": classification,
            "rationale": "Confirmed exploitation",
        },
    )["incident_id"]


def put_report(api, incident_id, stage, data, status=200):
    return call(api, "PUT", f"/incidents/{incident_id}/report-data/{stage}", status, json=data)


def get_report(api, incident_id, stage, status=200):
    return call(api, "GET", f"/incidents/{incident_id}/reports/{stage}", status)


def audit_events(api):
    return call(api, "GET", "/audit-logs", 200)["events"]


def bare_session():
    """A session without X-User-Id, for header-precedence checks."""
    return requests.Session()


# --- AC-08: report data and generation (REQ-07) ---


def test_ac08_complete_case_has_every_field_and_no_missing_fields(api):
    identifier = incident(api)
    for stage, data in STAGE_FIELDS.items():
        stored = put_report(api, identifier, stage, data)
        assert stored == {
            "incident_id": identifier,
            "stage": stage,
            "generated_at": CLOCK,
            "data": data,
            "missing_fields": [],
        }
    for stage, data in STAGE_FIELDS.items():
        report = get_report(api, identifier, stage)
        assert report["data"] == data
        assert report["missing_fields"] == []
        assert report["generated_at"] == CLOCK


def test_ac08_incomplete_case_lists_exactly_the_two_missing_72h_fields(api):
    identifier = incident(api)
    data = dict(STAGE_FIELDS["vulnerability_notification"])
    del data["exploit_nature"]
    data["user_mitigations"] = "   "
    put_report(api, identifier, "vulnerability_notification", data)
    report = get_report(api, identifier, "vulnerability_notification")
    assert report["missing_fields"] == ["exploit_nature", "user_mitigations"]
    assert report["data"] == data  # Stored exactly as sent, whitespace included.


def test_ac08_stage_without_data_lists_every_required_field(api):
    identifier = incident(api)
    for stage in STAGE_FIELDS:
        report = get_report(api, identifier, stage)
        assert report["data"] == {}
        assert report["missing_fields"] == REQUIRED[stage]


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "\t\n"],
    ids=["null", "empty", "spaces", "whitespace"],
)
def test_ac08_blank_or_null_required_string_is_missing(api, value):
    identifier = incident(api)
    data = dict(STAGE_FIELDS["final_report"], severity=value)
    report = put_report(api, identifier, "final_report", data)
    assert report["missing_fields"] == ["severity"]
    # Fail (not crash) if the field is dropped from data instead of stored as sent.
    assert report["data"].get("severity", "<absent>") == value


def test_ac08_empty_or_null_member_states_is_missing(api):
    identifier = incident(api)
    for value in ([], None):
        report = put_report(api, identifier, "early_warning", {"member_states": value})
        assert report["missing_fields"] == ["member_states"]


def test_ac08_optional_fields_are_never_missing(api):
    identifier = incident(api)
    data = {k: v for k, v in STAGE_FIELDS["final_report"].items() if k in REQUIRED["final_report"]}
    assert put_report(api, identifier, "final_report", data)["missing_fields"] == []
    data["malicious_actor_information"] = None
    assert put_report(api, identifier, "final_report", data)["missing_fields"] == []


def test_ac08_put_replaces_the_whole_stage(api):
    identifier = incident(api)
    put_report(
        api, identifier, "vulnerability_notification", STAGE_FIELDS["vulnerability_notification"]
    )
    put_report(api, identifier, "vulnerability_notification", {"product_information": "Only this"})
    report = get_report(api, identifier, "vulnerability_notification")
    assert report["data"] == {"product_information": "Only this"}
    assert report["missing_fields"] == REQUIRED["vulnerability_notification"][1:]
    # Other stages are untouched by a stage replacement.
    assert get_report(api, identifier, "early_warning")["data"] == {}


@pytest.mark.parametrize(
    ("stage", "body", "field"),
    [
        ("early_warning", {"severity": "high"}, "severity"),
        ("vulnerability_notification", {"member_states": ["DE"]}, "member_states"),
        ("final_report", {"sensitivity": "low"}, "sensitivity"),
        ("final_report", {"colour": "red"}, "colour"),
        ("final_report", {"severity": 3}, "severity"),
        ("final_report", {"severity": ["high"]}, "severity"),
        ("final_report", {"impact": True}, "impact"),
        ("early_warning", {"member_states": "DE"}, "member_states"),
        ("early_warning", {"member_states": ["DE", 7]}, "member_states"),
        ("early_warning", {"member_states": [None]}, "member_states"),
    ],
)
def test_ac08_bad_field_returns_400_naming_it_and_stores_nothing(api, stage, body, field):
    identifier = incident(api)
    before = put_report(api, identifier, stage, STAGE_FIELDS[stage])
    events = audit_events(api)
    error = put_report(api, identifier, stage, body, status=400)
    assert error["error"]["code"] == "INVALID_REQUEST"
    assert field in error["error"]["message"]
    assert get_report(api, identifier, stage)["data"] == before["data"]
    assert audit_events(api) == events


@pytest.mark.parametrize(
    ("raw", "content_type"),
    [
        ("[]", "application/json"),
        ('"text"', "application/json"),
        ("null", "application/json"),
        ("{", "application/json"),
        (b"\xff", "application/json"),
        ("", "application/json"),
    ],
    ids=["array", "string", "null", "malformed", "not-utf8", "empty"],
)
def test_ac08_non_object_or_invalid_json_body_is_400(api, raw, content_type):
    identifier = incident(api)
    response = api.request(
        "PUT",
        f"/incidents/{identifier}/report-data/final_report",
        data=raw,
        headers={"Content-Type": content_type},
    )
    assert response.status_code == 400, response.text
    assert get_report(api, identifier, "final_report")["data"] == {}


def test_ac08_check_order_header_then_incident_then_stage_then_body(api):
    identifier = incident(api)
    # Missing header comes first, even for an unknown incident and stage.
    response = api.request(
        "PUT", "/incidents/inc-missing/report-data/bogus", session=bare_session(), json={"x": 1}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    # Unknown incident beats invalid stage and invalid body.
    response = api.request("PUT", "/incidents/inc-missing/report-data/bogus", data="{")
    assert response.status_code == 404
    # Invalid stage beats invalid body.
    response = api.request("PUT", f"/incidents/{identifier}/report-data/bogus", data="{")
    assert response.status_code == 400
    assert "stage" in response.json()["error"]["message"]
    # GET: unknown incident first, then stage. Only the status is agreed here:
    # the pod checks exact error codes only for explicitly agreed cases.
    get_report(api, "inc-missing", "bogus", status=404)
    assert "stage" in get_report(api, identifier, "bogus", status=400)["error"]["message"]


def test_ac08_get_stores_and_audits_nothing_and_uses_the_clock(api):
    identifier = incident(api)
    put_report(api, identifier, "early_warning", STAGE_FIELDS["early_warning"])
    events = audit_events(api)
    call(api, "PUT", "/test/clock", 200, json={"now": "2026-11-05T08:30:00.250000Z"})
    report = get_report(api, identifier, "early_warning")
    assert report["generated_at"] == "2026-11-05T08:30:00.250000Z"
    assert audit_events(api) == events


def test_ac08_voluntary_incident_and_final_report_before_fix_are_allowed(api):
    identifier = incident(api, classification="voluntary")
    report = put_report(api, identifier, "final_report", STAGE_FIELDS["final_report"])
    assert report["missing_fields"] == []
    assert call(api, "GET", f"/incidents/{identifier}", 200)["fix_available_at"] is None


def test_ac08_reset_removes_report_data(api):
    identifier = incident(api)
    put_report(api, identifier, "early_warning", STAGE_FIELDS["early_warning"])
    call(api, "POST", "/test/reset", 204)
    get_report(api, identifier, "early_warning", status=404)


# --- AC-09: append-only audit log (REQ-08) ---


def _sbom(components):
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": components}


def test_ac09_every_change_is_logged_chronologically_with_user_and_clock(api):
    def at(now):
        call(api, "PUT", "/test/clock", 200, json={"now": now})

    at("2026-11-02T09:00:00Z")
    release = call(
        api,
        "POST",
        "/releases",
        201,
        headers={"X-User-Id": "release-manager"},
        json={"product": "AuditRouter", "version": "1.0", "support_end_date": "2027-01-01"},
    )["release_id"]
    at("2026-11-02T09:05:00Z")
    call(
        api,
        "PUT",
        f"/releases/{release}/sbom",
        200,
        headers={"X-User-Id": "build-bot"},
        json=_sbom([]),
    )
    at("2026-11-02T09:06:00Z")
    call(
        api,
        "PUT",
        f"/releases/{release}/sbom",
        200,
        headers={"X-User-Id": "build-bot"},
        json=_sbom([{"type": "library", "name": "zlib", "version": "1.3"}]),
    )
    at("2026-11-02T10:00:00.500000Z")
    identifier = incident(api, user="security-engineer")
    at("2026-11-02T11:00:00Z")
    call(
        api,
        "PATCH",
        f"/incidents/{identifier}",
        200,
        headers={"X-User-Id": "security-engineer"},
        json={"fix_available_at": "2026-11-02T10:30:00Z"},
    )
    at("2026-11-02T12:00:00Z")
    call(
        api,
        "POST",
        f"/incidents/{identifier}/submissions",
        201,
        headers={"X-User-Id": "compliance-officer"},
        json={"stage": "early_warning", "submitted_at": "2026-11-01T20:00:00Z"},
    )
    at("2026-11-02T13:00:00Z")
    call(
        api,
        "PUT",
        f"/incidents/{identifier}/report-data/early_warning",
        200,
        headers={"X-User-Id": "compliance-officer"},
        json=STAGE_FIELDS["early_warning"],
    )

    events = audit_events(api)
    assert [
        (e["timestamp"], e["user_id"], e["action"], e["entity_type"], e["entity_id"])
        for e in events
    ] == [
        ("2026-11-02T09:00:00Z", "release-manager", "RELEASE_REGISTERED", "release", release),
        ("2026-11-02T09:05:00Z", "build-bot", "SBOM_STORED", "release", release),
        ("2026-11-02T09:06:00Z", "build-bot", "SBOM_REPLACED", "release", release),
        (
            "2026-11-02T10:00:00.500000Z",
            "security-engineer",
            "INCIDENT_CREATED",
            "incident",
            identifier,
        ),
        (
            "2026-11-02T11:00:00Z",
            "security-engineer",
            "FIX_AVAILABLE_RECORDED",
            "incident",
            identifier,
        ),
        (
            "2026-11-02T12:00:00Z",
            "compliance-officer",
            "SUBMISSION_RECORDED",
            "incident",
            identifier,
        ),
        (
            "2026-11-02T13:00:00Z",
            "compliance-officer",
            "REPORT_DATA_STORED",
            "incident",
            identifier,
        ),
    ]
    assert len({e["event_id"] for e in events}) == len(events)
    assert events[5]["details"]["stage"] == "early_warning"
    assert events[6]["details"]["stage"] == "early_warning"


def test_ac09_equal_timestamps_keep_recording_order(api):
    # The api fixture freezes the clock, so all of these share one timestamp.
    first = api.create({"product": "Tie", "version": "1", "support_end_date": "2027-01-01"})
    second = api.create({"product": "Tie", "version": "2", "support_end_date": "2027-01-01"})
    identifier = incident(api)
    events = audit_events(api)
    assert {e["timestamp"] for e in events} == {CLOCK}
    assert [e["entity_id"] for e in events] == [
        first["release_id"],
        second["release_id"],
        identifier,
    ]


def test_ac09_failures_reads_and_test_controls_record_nothing(api):
    release = api.create()["release_id"]
    identifier = incident(api)
    baseline = audit_events(api)
    # Failed changes.
    call(
        api,
        "POST",
        "/releases",
        409,
        json={"product": "TestRouter", "version": "1.0", "support_end_date": "2027-01-01"},
    )
    call(api, "POST", "/releases", 400, json={"product": "Bad"})
    call(api, "PUT", f"/releases/{release}/sbom", 400, json={"bomFormat": "CycloneDX"})
    call(api, "PUT", "/releases/rel-missing/sbom", 404, json=_sbom([]))
    call(api, "POST", "/incidents", 400, json={"classification": "mandatory"})
    call(
        api,
        "PATCH",
        f"/incidents/{identifier}",
        400,
        json={"fix_available_at": "2020-01-01T00:00:00Z"},
    )
    call(
        api,
        "POST",
        f"/incidents/{identifier}/submissions",
        400,
        json={"stage": "final_report", "submitted_at": "2026-11-01T01:00:00Z"},
    )
    response = api.request(
        "POST",
        "/releases",
        session=bare_session(),
        json={"product": "N", "version": "1", "support_end_date": "2027-01-01"},
    )
    assert response.status_code == 400
    # Reads and test controls.
    call(api, "GET", f"/releases/{release}", 200)
    call(api, "GET", f"/releases/{release}/components", 200)
    call(api, "GET", f"/incidents/{identifier}", 200)
    get_report(api, identifier, "early_warning")
    call(api, "PUT", "/test/clock", 200, json={"now": "2026-11-03T00:00:00Z"})
    assert audit_events(api) == baseline


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_ac09_audit_entries_cannot_be_edited_or_deleted(api, method):
    api.create()
    events = audit_events(api)
    for event_id in (events[0]["event_id"], "evt-does-not-exist"):
        response = api.request(method, f"/audit-logs/{event_id}", json={"user_id": "attacker"})
        assert response.status_code == 405, response.text
    assert audit_events(api) == events


def test_ac09_reset_clears_the_audit_log(api):
    api.create()
    assert audit_events(api)
    call(api, "POST", "/test/reset", 204)
    assert audit_events(api) == []


# --- Agreed Phase 4 input case (pod Phase 5 Q7) ---


@pytest.mark.parametrize(
    "content_type",
    [
        "application/vnd.cyclonedx+json",
        "application/vnd.cyclonedx+json; charset=utf-8",
        "Application/JSON",
    ],
)
def test_q7_cyclonedx_media_types_are_accepted(api, shared_sbom, content_type):
    release = api.create()["release_id"]
    response = api.request(
        "PUT",
        f"/releases/{release}/sbom",
        data=json.dumps(shared_sbom),
        headers={"Content-Type": content_type},
    )
    assert response.status_code == 200, response.text
    assert response.json()["component_count"] == 25


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/xml"])
def test_q7_other_or_missing_content_type_is_400(api, content_type):
    release = api.create()["release_id"]
    session = requests.Session()
    session.headers["X-User-Id"] = "phase5-test"
    request = requests.Request(
        "PUT",
        f"{api.base_url}/releases/{release}/sbom",
        data=b'{"bomFormat":"CycloneDX","specVersion":"1.6","version":1,"components":[]}',
        headers={"Content-Type": content_type} if content_type else {},
    )
    prepared = session.prepare_request(request)
    if content_type is None:
        prepared.headers.pop("Content-Type", None)
    response = session.send(prepared, timeout=10)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert api.components(release) == []
