"""Adapter regressions independent of cloud resources and existing databases."""

import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest
from autograder.config import TEAM2, TEAM6, HarnessError, Settings, normalize_target, session_id
from autograder.runner import EXPECTED_TESTS, parse_junit


@pytest.fixture
def settings(monkeypatch):
    # Core subprocess tests must never probe the real public service.
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
    assert error.value.status == 500


def test_system_cannot_run_against_partner(settings):
    with pytest.raises(HarnessError):
        replace(settings, role="system").authorize(TEAM6)


@pytest.mark.parametrize("value", [None, 2, ""])
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


@pytest.mark.parametrize("duplicate", [True, False])
def test_junit_rejects_count_correct_but_incomplete_suite(tmp_path, duplicate):
    root = ET.Element("testsuite")
    for index in range(EXPECTED_TESTS):
        ET.SubElement(
            root,
            "testcase",
            classname="app.cra-service.test_api",
            name="test_repeated" if duplicate else f"test_original_{index}",
            time="0",
        )
    path = tmp_path / "misleading.xml"
    ET.ElementTree(root).write(path)
    report = parse_junit(path, 0)
    assert report["summary"]["passed"] == EXPECTED_TESTS  # Preserve real record counts.
    assert report["result"] == "error"  # Counts alone must not certify the full suite.


@pytest.mark.parametrize("missing_groups", [False, True])
def test_junit_requires_phase4_acceptance_groups(tmp_path, missing_groups):
    root = ET.Element("testsuite")
    for index in range(157):
        ET.SubElement(
            root,
            "testcase",
            classname="app.cra-service.test_api",
            name=f"test_ac01_original_{index}",
            time="0",
        )
    for number, count in ((4, 10), (5, 11), (6, 62), (7, 113)):
        for index in range(count):
            name = (
                f"test_ac04_wrong_{number}_{index}"
                if missing_groups
                else f"test_ac{number:02d}_case_{index}"
            )
            ET.SubElement(
                root, "testcase", classname="app.cra-service.test_phase4_api", name=name, time="0"
            )
    path = tmp_path / "groups.xml"
    ET.ElementTree(root).write(path)
    report = parse_junit(path, 0)
    assert report["result"] == ("error" if missing_groups else "pass")
    assert report["summary"]["total"] == report["summary"]["passed"] == EXPECTED_TESTS


def test_tester_does_not_implicitly_approve_peer_reset_targets(monkeypatch):
    monkeypatch.delenv("AUTOGRADER_APPROVED_TARGETS", raising=False)
    monkeypatch.delenv("AUTOGRADER_DEFAULT_TARGET", raising=False)
    monkeypatch.setenv("AUTOGRADER_ENABLED", "true")
    monkeypatch.setenv("AUTOGRADER_ALLOW_RESET", "true")
    monkeypatch.setenv("AUTOGRADER_DATABASE_URL", "unused-test-dsn")
    configured = Settings.environment("tester")
    assert configured.authorize(TEAM2) == TEAM2
    with pytest.raises(HarnessError, match="explicitly approved"):
        configured.authorize(TEAM6)


def test_bad_xml_cannot_be_interpreted_as_success(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<broken")
    with pytest.raises(ET.ParseError):
        parse_junit(path, 0)
