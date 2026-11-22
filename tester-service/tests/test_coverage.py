"""HTTP observations must not become fabricated source/model coverage."""

from autograder.coverage import (
    is_own_system,
    model_coverage,
    operation_coverage,
    unavailable_coverage,
)


def test_operation_measurement_counts_responses_and_keeps_missing_operations(tmp_path):
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        "paths:\n  /releases:\n    parameters: []\n    post: {}\n    get: {}\n  /report:\n    get: {}\n"
    )
    observations = [
        {"method": "POST", "path": "/releases", "status": 201},
        {"method": "POST", "path": "/releases", "status": 400},
        {"method": "GET", "path": "/releases", "status": None},
        {"method": "GET", "path": "/outside-contract", "status": 200},
    ]
    result = operation_coverage(observations, contract)
    assert result["observed"] == 1 and result["total"] == 3
    assert result["missing"] == ["GET /releases", "GET /report"]
    assert result["operations"][0]["status_codes"] == {"201": 1, "400": 1}
    assert result["operations"][0]["responses"] == 2
    assert "percent" not in result
    # Bind the denominator to the exact specification, not an inferred API list.
    before = result["contract_sha256"]
    contract.write_text(contract.read_text() + "  /new:\n    get: {}\n")
    changed = operation_coverage(observations, contract)
    assert changed["total"] == 4 and changed["contract_sha256"] != before


def test_failed_http_response_is_observed_but_not_a_passing_coverage_claim(tmp_path):
    contract = tmp_path / "contract.yaml"
    contract.write_text("paths:\n  /releases:\n    post: {}\n")
    measured = operation_coverage(
        [{"method": "POST", "path": "/releases", "status": 500}], contract
    )
    assert measured["observed"] == 1
    assert measured["operations"][0]["status_codes"] == {"500": 1}
    assert "error responses" in measured["limitation"]


def test_absent_measurements_are_unavailable_not_zero_or_full_coverage():
    report = unavailable_coverage()
    assert set(report) == {"code", "component", "system", "http_operations"}
    for metric in report.values():
        assert metric["status"] == "unavailable"
        assert metric["percent"] is None and metric["reason"]


def test_model_coverage_only_for_own_system(monkeypatch):
    monkeypatch.delenv("AUTOGRADER_OWN_TARGETS", raising=False)
    assert is_own_system("https://cra-phase3-api-456725640364.us-central1.run.app/api/v1")
    assert not is_own_system("http://136.116.160.182:8080")
    monkeypatch.setenv("AUTOGRADER_OWN_TARGETS", "http://127.0.0.1:18080")
    assert is_own_system("http://127.0.0.1:18080/")


def test_model_coverage_counts_executed_witnesses_not_skips(tmp_path):
    design = tmp_path / "design.json"
    design.write_text(
        '{"version": "t", "mapping": "m", "requirements": ['
        '{"id": "DR-A", "witnesses": ["f.py::test_a"]},'
        '{"id": "DR-B", "witnesses": ["f.py::test_b", "f.py::test_c"]},'
        '{"id": "DR-C", "witnesses": ["scripts/outside.py"]}]}'
    )
    results = [
        {"test_id": "f.py::test_a[param-1]", "outcome": "fail"},
        {"test_id": "f.py::test_b", "outcome": "pass"},
        {"test_id": "f.py::test_c", "outcome": "skip"},
    ]
    coverage = model_coverage(results, design)
    assert coverage["covered"] == 1 and coverage["total"] == 3
    assert coverage["requirements"] == ["DR-A"]
