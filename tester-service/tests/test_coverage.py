"""HTTP observations must not become fabricated source/model coverage."""

from autograder.coverage import operation_coverage, unavailable_coverage


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
