"""Reject invented measures and require attributed target execution."""

import copy
import json

import pytest
from autograder.measured_coverage import digest, measured_coverage


@pytest.fixture
def measurement(tmp_path):
    root = tmp_path / "repo"
    (root / "cra-service").mkdir(parents=True)
    (root / "docs").mkdir()
    source = root / "cra-service/alpha.py"
    source.write_text("def used():\n    return 1\n\ndef unused():\n    return 2\n")
    for name in ("test_api.py", "test_phase4_api.py"):
        (root / "cra-service" / name).write_text("# measured test source\n")
    model = {
        "version": "test-proposal",
        "source_files": ["alpha.py"],
        "components": [
            {"id": "used", "functions": {"alpha.py": ["used"]}},
            {"id": "unused", "functions": {"alpha.py": ["unused"]}},
        ],
        "transitions": [
            {"id": "transition", "test": "test_api::test_state_change", "components": ["used"]}
        ],
    }
    (root / "docs/coverage-model.json").write_text(json.dumps(model))
    directory = tmp_path / "evidence"
    directory.mkdir()
    run_id = "coverage-system-" + "a" * 32
    metadata = {
        "run_id": run_id,
        "coverage_version": "7.17.2",
        "source_sha256": {"cra-service/alpha.py": digest(source)},
        "test_sha256": {
            "cra-service/" + n: digest(root / "cra-service" / n)
            for n in ("test_api.py", "test_phase4_api.py")
        },
    }
    raw = {
        "meta": {"version": "7.17.2", "branch_coverage": True},
        "files": {
            "/app/cra-service/alpha.py": {
                "summary": {"num_statements": 4, "num_branches": 0, "covered_branches": 0},
                "executed_lines": [2],
                "missing_lines": [1, 4, 5],
                "contexts": {"2": [run_id + "|cra-service/test_api.py::test_state_change"]},
            }
        },
    }
    report = {
        "session_id": run_id,
        "checks": [
            {
                "id": "cra-service.test_api::test_state_change",
                "title": "test_state_change",
                "passed": True,
            }
        ],
    }

    def save():
        (directory / "metadata.json").write_text(json.dumps(metadata))
        (directory / "server-coverage.json").write_text(json.dumps(raw))

    save()
    return root, directory, report, metadata, raw, save


def test_measures_statements_components_and_transitions_with_distinct_denominators(measurement):
    root, directory, report, *_ = measurement
    result = measured_coverage(root, directory, report)
    assert result["code"]["percent"] == 25
    assert result["code"]["covered"] == 1 and result["code"]["total"] == 4
    assert result["component"]["covered"] == 1 and result["component"]["total"] == 2
    assert result["component"]["percent"] == 50
    assert result["system"]["covered"] == 1 and result["system"]["total"] == 1
    assert result["system"]["items"][0]["tests"] == ["test_api::test_state_change"]
    assert result["system"]["proposed_measure"] is True
    assert result["code"]["branches"]["percent"] is None


def test_failed_assertion_cannot_certify_model_transition_but_execution_is_still_measured(
    measurement,
):
    root, directory, report, *_ = measurement
    report = copy.deepcopy(report)
    report["checks"][0]["passed"] = False
    result = measured_coverage(root, directory, report)
    assert result["component"]["covered"] == 1
    assert result["code"]["percent"] == 25
    assert result["system"]["covered"] == 0


@pytest.mark.parametrize(
    "change",
    ["session", "source", "test_source", "missing_file", "unattributed", "unattributed_line"],
)
def test_missing_or_mismatched_evidence_never_becomes_coverage(measurement, change):
    root, directory, report, metadata, raw, save = measurement
    if change == "session":
        report["session_id"] = "another-run"
    elif change == "source":
        (root / "cra-service/alpha.py").write_text("# changed source")
    elif change == "test_source":
        (root / "cra-service/test_api.py").write_text("# changed assertions")
    elif change == "missing_file":
        raw["files"] = {}
    elif change == "unattributed_line":
        raw["files"]["/app/cra-service/alpha.py"]["executed_lines"].append(5)
    else:
        raw["files"]["/app/cra-service/alpha.py"]["contexts"] = {
            "2": [metadata["run_id"] + "|unattributed"]
        }
    save()
    with pytest.raises(ValueError):
        measured_coverage(root, directory, report)


def test_passing_test_without_execution_of_required_component_is_not_a_model_witness(measurement):
    root, directory, report, *_ = measurement
    model_path = root / "docs/coverage-model.json"
    model = json.loads(model_path.read_text())
    model["transitions"][0]["components"] = ["unused"]
    model_path.write_text(json.dumps(model))
    result = measured_coverage(root, directory, report)
    assert result["system"]["covered"] == 0
