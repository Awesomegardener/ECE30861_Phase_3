"""Adapter regressions independent of cloud resources and existing databases."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest
from autograder.api import Harness
from autograder.config import TEAM2, TEAM6, HarnessError, Settings, normalize_target, session_id
from autograder.runner import Runner, parse_junit


@pytest.fixture
def settings(monkeypatch):
    # Core subprocess tests must never probe the real public service.
    monkeypatch.setattr("autograder.runner.verify_public_target", lambda _: None)
    return Settings(
        "tester", True, True, "unused-test-dsn", TEAM2, frozenset({TEAM2, TEAM6}), "", 10
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1",
        "https://evil.example",
        "https://cra-phase3-api-456725640364.us-central1.run.app.evil.example",
    ],
)
def test_allowlist_rejects_unapproved_origins(settings, value):
    with pytest.raises(HarnessError) as error:
        settings.authorize(value)
    assert error.value.status == 400


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        "",
        "file:///tmp",
        "https://user:pass@example.com",
        TEAM2 + "?x=1",
        TEAM2 + "#x",
        TEAM2 + "/other",
        " " + TEAM2,
        "http://example.com:bad",
    ],
)
def test_invalid_targets(value):
    with pytest.raises(HarnessError):
        normalize_target(value)


@pytest.mark.parametrize("target", [TEAM2, TEAM6, TEAM2 + "/api/v1/", TEAM6 + "/"])
def test_approved_target_normalization(settings, target):
    assert settings.authorize(target) in {TEAM2, TEAM6}


@pytest.mark.parametrize(
    "changes", [dict(enabled=False), dict(allow_reset=False), dict(database_url="")]
)
def test_controls_fail_closed(settings, changes):
    with pytest.raises(HarnessError) as error:
        replace(settings, **changes).authorize()
    assert error.value.status == 503


def test_system_cannot_run_against_partner(settings):
    with pytest.raises(HarnessError):
        replace(settings, role="system").authorize(TEAM6)


@pytest.mark.parametrize("value", [None, 2, "", "../unsafe/session", "a" * 129, "a&session=x"])
def test_session_identifiers_are_bounded(value):
    with pytest.raises(HarnessError):
        session_id(value)


@pytest.mark.parametrize(
    "tag,code,result",
    [
        (None, 0, "pass"),
        ("failure", 1, "fail"),
        ("error", 1, "error"),
        ("skipped", 0, "error"),
        (None, 5, "error"),
    ],
)
def test_junit_outcomes_are_real(tmp_path, tag, code, result):
    root = ET.Element("testsuites")
    case = ET.SubElement(ET.SubElement(root, "testsuite"), "testcase", name="test_ac01", time="0.1")
    if tag:
        ET.SubElement(case, tag, message="Actual assertion or fixture failure")
    xml = tmp_path / "results.xml"
    ET.ElementTree(root).write(xml)
    report = parse_junit(xml, code, expected_count=1)
    assert report["result"] == result
    assert report["summary"]["total"] == 1
    assert report["checks"][0]["passed"] == (tag is None)
    assert report["summary"]["passed"] == int(tag is None)


def test_incomplete_collection_cannot_pass(tmp_path):
    path = tmp_path / "empty.xml"
    path.write_text("<testsuites/>")
    assert parse_junit(path, 0)["result"] == "error"


def test_bad_xml_cannot_be_interpreted_as_success(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<broken")
    with pytest.raises(ET.ParseError):
        parse_junit(path, 0)


def test_runner_terminates_timed_out_child(settings, monkeypatch):
    real_popen = subprocess.Popen
    children = []

    def sleeping_child(command, **kwargs):
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr("autograder.runner.subprocess.Popen", sleeping_child)
    with pytest.raises(TimeoutError):
        Runner(replace(settings, timeout=1)).execute(TEAM2, lambda: None)
    assert len(children) == 1 and children[0].poll() is not None


def test_runner_stops_if_lock_database_connection_is_lost(settings, monkeypatch):
    real_popen = subprocess.Popen
    children = []

    def sleeping_child(command, **kwargs):
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(child)
        return child

    def unavailable():
        raise ConnectionError("Lease connection lost")

    monkeypatch.setattr("autograder.runner.subprocess.Popen", sleeping_child)
    with pytest.raises(ConnectionError):
        Runner(settings).execute(TEAM2, unavailable)
    assert children[0].poll() is not None


def test_optional_clock_is_system_only(settings):
    with pytest.raises(HarnessError):
        Harness(settings).validate({"now": "2026-11-01T00:00:00Z"})


def test_explicit_null_target_is_not_a_missing_optional_field(settings):
    with pytest.raises(HarnessError) as error:
        Harness(settings).validate({"target_base_url": None})
    assert error.value.status == 400
