"""Coverage availability and observed HTTP operations, never inferred source coverage."""

import hashlib
from collections import Counter

import yaml  # type: ignore[import-untyped]

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def unavailable_coverage():
    reasons = {
        "code": "Target-side source instrumentation and revision are not available to this HTTP runner",
        "component": "No attributed server traces supplied for this run; Team 2's proposed mapping is not grader-confirmed",
        "system": "No attributed server execution and behavioral transition witnesses supplied for this run",
        "http_operations": "No HTTP evidence collected for this session",
    }
    return {
        name: {"status": "unavailable", "percent": None, "reason": reason}
        for name, reason in reasons.items()
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
