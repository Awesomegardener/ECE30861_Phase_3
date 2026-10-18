"""Verify useful report evidence and avoid leaking routine authentication material."""

import datetime
import json
from pathlib import Path

import pytest
import requests
from conftest import Api
from http_evidence import HttpEvidence, utc_now
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
TESTED_COMMIT = "a" * 40


def recorder(directory, **kwargs):
    return HttpEvidence(
        ROOT,
        directory,
        "https://runner:url-secret@service.invalid/api/v1?token=query-secret",
        tested_commit=TESTED_COMMIT,
        **kwargs,
    )


def response(payload, *, status=200, request_body=None):
    result = requests.Response()
    result.status_code = status
    result._content = payload
    result.headers = {
        "Content-Type": "application/json",
        "X-Request-Id": "request-example",
        "Set-Cookie": "session=cookie-secret",
    }
    result.request = requests.Request(
        "PUT",
        "https://runner:url-secret@service.invalid/api/v1/test/clock?token=query-secret",
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer header-secret",
            "X-Api-Key": "api-secret",
            "Cookie": "session=cookie-secret",
            "X-User-Id": "test-user",
        },
    ).prepare()
    return result


def observe(evidence, result):
    evidence.record(
        {
            "test_id": "test_example",
            "method": "PUT",
            "path": "/api/v1/test/clock",
            "status": result.status_code,
            "documented": True,
            "schema_validation": "passed",
            "requested_at_utc": utc_now(),
            "received_at_utc": utc_now(),
            "seconds": 0.01,
        },
        response=result,
    )


def test_evidence_records_provenance_and_redacted_json(tmp_path):
    evidence = recorder(tmp_path, capture_bodies=True)
    observe(
        evidence,
        response(
            b'{"now":"2026-11-01T23:59:59Z","access_token":"body-secret"}',
            request_body='{"now":"2026-11-01T23:59:59Z","nested":[{"password":"password-secret"}]}',
        ),
    )
    saved = json.loads(evidence.write().read_text())
    assert saved["run"]["tested_commit_sha"] == TESTED_COMMIT
    assert "operator supplied" in saved["run"]["target_version_provenance"]
    assert len(saved["run"]["runner_commit_sha"]) == 40
    assert isinstance(saved["run"]["runner_worktree_dirty"], bool)
    assert "cra-service/main.py" in saved["run"]["runner_source_sha256"]
    assert "docs/openapi.yaml" in saved["run"]["shared_input_sha256"]
    assert saved["run"]["target_base_url"].startswith("https://service.invalid/api/v1")
    for field in ("started_at_utc", "completed_at_utc"):
        value = saved["run"][field]
        assert value.endswith("Z")
        assert datetime.datetime.fromisoformat(value).utcoffset() == datetime.timedelta(0)
    exchange = saved["exchanges"][0]
    assert exchange["status"] == 200 and exchange["schema_validation"] == "passed"
    assert exchange["response"]["headers"]["X-Request-Id"] == "request-example"
    assert exchange["request"]["body"]["value"]["now"] == "2026-11-01T23:59:59Z"
    assert not exchange["request"]["body"]["truncated"]
    serialized = json.dumps(saved)
    for secret in (
        "url-secret",
        "query-secret",
        "header-secret",
        "api-secret",
        "cookie-secret",
        "body-secret",
        "password-secret",
    ):
        assert secret not in serialized


def test_evidence_keeps_malformed_text_and_empty_204(tmp_path):
    evidence = recorder(tmp_path, capture_bodies=True)
    observe(
        evidence,
        response(
            b'{"error":{"code":"INVALID_JSON","message":"Malformed JSON payload"}}',
            status=400,
            request_body='{"password": "raw-secret"',
        ),
    )
    observe(evidence, response(b"", status=204))
    saved = json.loads(evidence.write().read_text())
    bad, empty = saved["exchanges"]
    assert bad["status"] == 400 and bad["request"]["body"]["kind"] == "text"
    assert "raw-secret" not in json.dumps(saved)
    assert bad["response"]["body"]["value"]["error"]["code"] == "INVALID_JSON"
    assert empty["response"]["body"] == {"kind": "empty", "bytes": 0}


def test_evidence_body_capture_is_opt_in(tmp_path):
    evidence = recorder(tmp_path)
    observe(evidence, response(b'{"private":"body-secret"}', request_body="request-secret"))
    saved = json.loads(evidence.write().read_text())
    assert not saved["run"]["bodies_captured"]
    assert "body" not in saved["exchanges"][0]["request"]
    assert "body" not in saved["exchanges"][0]["response"]
    assert "body-secret" not in json.dumps(saved)


def test_evidence_marks_truncated_bodies(tmp_path):
    evidence = recorder(tmp_path, capture_bodies=True, body_limit=20)
    observe(evidence, response(json.dumps({"name": "x" * 200}).encode()))
    saved = json.loads(evidence.write().read_text())
    body = saved["exchanges"][0]["response"]["body"]
    assert body["truncated"] and len(body["preview"]) == 20
    assert body["bytes"] > 200 and len(body["sha256"]) == 64


def test_evidence_preserves_failed_schema_response(tmp_path, contract, monkeypatch):
    evidence = recorder(tmp_path, capture_bodies=True)
    api = Api("https://service.invalid", contract, evidence)
    result = response(b'{"unexpected":"invalid-release-response"}')
    monkeypatch.setattr(api.session, "request", lambda *args, **kwargs: result)
    try:
        with pytest.raises(ValidationError):
            api.request("GET", "/releases/example")
    finally:
        api.session.close()
    saved = json.loads(evidence.write().read_text())
    exchange = saved["exchanges"][0]
    assert exchange["schema_validation"] == "failed"
    assert exchange["response"]["body"]["value"] == {"unexpected": "invalid-release-response"}


def test_evidence_preserves_transport_failure(tmp_path, contract, monkeypatch):
    evidence = recorder(tmp_path, capture_bodies=True)
    api = Api("https://service.invalid", contract, evidence)

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Bearer transport-secret")

    monkeypatch.setattr(api.session, "request", unavailable)
    try:
        with pytest.raises(requests.ConnectionError):
            api.request("GET", "/releases/example")
    finally:
        api.session.close()
    saved = json.loads(evidence.write().read_text())
    exchange = saved["exchanges"][0]
    assert exchange["status"] is None and exchange["response"] is None
    assert exchange["request_error"] == "ConnectionError"
    assert "transport-secret" not in json.dumps(saved)
    assert json.loads((tmp_path / "operation-observations.json").read_text()) == []


def test_evidence_retains_separate_runs(tmp_path):
    first = recorder(tmp_path).write()
    original = first.read_bytes()
    second = recorder(tmp_path).write()
    assert first != second and first.read_bytes() == original
    assert first.exists() and second.exists()


@pytest.mark.parametrize("message", ["", " \t\n"])
def test_error_envelope_checks_reject_empty_messages(tmp_path, contract, monkeypatch, message):
    evidence = recorder(tmp_path, capture_bodies=True)
    api = Api("https://service.invalid", contract, evidence)
    result = response(
        json.dumps({"error": {"code": "UNMAPPED_CODE", "message": message}}).encode(), status=404
    )
    monkeypatch.setattr(api.session, "request", lambda *args, **kwargs: result)
    try:
        with pytest.raises(AssertionError, match="Error message must explain"):
            api.request("GET", "/releases/example")
    finally:
        api.session.close()
    saved = json.loads(evidence.write().read_text())
    assert saved["exchanges"][0]["schema_validation"] == "failed"


def test_error_envelope_accepts_unagreed_code_values(tmp_path, contract, monkeypatch):
    evidence = recorder(tmp_path)
    api = Api("https://service.invalid", contract, evidence)
    result = response(
        b'{"error":{"code":"OTHER_TEAM_CODE","message":"Release not found"}}', status=404
    )
    monkeypatch.setattr(api.session, "request", lambda *args, **kwargs: result)
    try:
        assert api.request("GET", "/releases/example").status_code == 404
    finally:
        api.session.close()
