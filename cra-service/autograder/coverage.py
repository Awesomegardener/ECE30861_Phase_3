"""Coverage availability and observed HTTP operations, never inferred source coverage."""

import hashlib
from collections import Counter

import yaml  # type: ignore[import-untyped]

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def unavailable_coverage(code_reason=None):
    reasons = {
        "code": code_reason or "Source instrumentation unavailable on this system instance",
        "component": "Pod Phase 2 sections 2/7 list capabilities and implementation choices, but no shared component denominator and exercise rules; unavailable",
        "system": "Pod AC-01 through AC-10; no complete scenario dispatch evidence available",
        "http_operations": "No HTTP evidence collected for this session",
    }
    return {
        name: {
            "covered": None,
            "total": None,
            "basis": reason,
            "status": "unavailable",
            "percent": None,
            "reason": reason,
        }
        for name, reason in reasons.items()
    }


def acceptance_coverage(exchanges):
    """Pod Q4.1 scenarios, counted from dispatched inputs, never pass rates.

    Each witness is (canonical test-name fragment, method, pod path, minimum
    dispatches). Complete required scenarios must all appear. AC-08/09/10 have
    no suite witnesses, so remain uncovered in the denominator of ten.
    """
    sbom = "/api/v1/releases/{releaseId}/sbom"
    release = "/api/v1/releases"
    cve = "/api/v1/vulnerabilities/{cveId}/affected-releases"
    incident = "/api/v1/incidents"
    rules = {
        "AC-01": [
            ("test_ac01_shared_release_cases", "POST", release, 4),
            ("test_ac01_support_boundary", "GET", release + "/{releaseId}", 3),
        ],
        "AC-02": [
            ("test_ac02_shared_25_components_are_isolated", "PUT", sbom, 1),
            (
                "test_ac02_shared_25_components_are_isolated",
                "GET",
                release + "/{releaseId}/components",
                3,
            ),
        ],
        "AC-03": [
            ("test_ac03_invalid_sbom_never_changes_inventory[empty-" + kind + "]", "PUT", sbom, 1)
            for kind in ["malformed", "bomFormat", "plaintext"]
        ]
        + [("test_ac03_unknown_release_stores_nothing", "PUT", sbom, 1)],
        "AC-04": [
            ("test_ac04_five_cves_exact_precision_recall_grouping_and_latency", "GET", cve, 5)
        ],
        "AC-05": [("test_ac05_known_unaffected_unknown_and_outage_are_distinct", "GET", cve, 3)],
        "AC-06": [
            (
                "test_ac06_create_read_preserves_awareness_actor_classification_rationale",
                "POST",
                incident,
                2,
            ),
            (
                "test_ac06_create_read_preserves_awareness_actor_classification_rationale",
                "GET",
                incident + "/{incidentId}",
                2,
            ),
            ("test_ac06_missing_incident_fields[rationale]", "POST", incident, 1),
            ("test_ac06_invalid_incident_fields[classification-unknown]", "POST", incident, 1),
        ],
        "AC-07": [
            ("test_ac07_exact_acceptance_sequence_and_independent_statuses", method, path, count)
            for method, path, count in [
                ("POST", incident, 1),
                ("POST", incident + "/{incidentId}/submissions", 2),
                ("PATCH", incident + "/{incidentId}", 1),
                ("GET", incident + "/{incidentId}", 1),
            ]
        ],
    }
    covered = []
    for criterion, witnesses in rules.items():
        if all(
            sum(
                selector in e.get("test_id", "")
                and e.get("method") == method
                and e.get("path") == path
                for e in exchanges
            )
            >= minimum
            for selector, method, path, minimum in witnesses
        ):
            covered.append(criterion)
    return {
        "covered": len(covered),
        "total": 10,
        "basis": "Pod Phase 2 Q4.1 AC-01–AC-10; coverage means all mapped scenario inputs dispatched, irrespective of pass/fail. AC-08/09/10 are not exercised by this suite; manual review is not claimed.",
        "criteria": covered,
    }


def operation_coverage(exchanges, contract_path):
    """Count contract operations receiving any HTTP response, including failures.

    An observed operation is not necessarily correct or covered in all states.
    Count across the full evidence bundle before its examples are truncated.
    """
    raw = contract_path.read_bytes()
    contract = yaml.safe_load(raw)
    operations: dict[tuple[str, str], Counter[int]] = {
        (method.upper(), path): Counter()
        for path, item in contract["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }
    for exchange in exchanges:
        key = (exchange.get("method"), exchange.get("path"))
        status = exchange.get("status")
        if key in operations and type(status) is int and 100 <= status <= 599:
            operations[key][status] += 1
    observed = sum(bool(statuses) for statuses in operations.values())
    return {
        "status": "measured",
        "metric": "shared-contract operations with at least one received HTTP response",
        "limitation": "Includes error responses; does not measure source, component or model-transition coverage",
        "contract_sha256": hashlib.sha256(raw).hexdigest(),
        "observed": observed,
        "total": len(operations),
        "missing": [
            f"{method} {path}" for (method, path), codes in operations.items() if not codes
        ],
        "operations": [
            {
                "method": method,
                "path": path,
                "responses": sum(codes.values()),
                "status_codes": {str(code): count for code, count in sorted(codes.items())},
            }
            for (method, path), codes in operations.items()
        ],
    }
