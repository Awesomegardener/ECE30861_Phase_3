"""Complete, unique suite results from an incremental child journal."""

import hashlib
import json

from http_evidence import redact_text

from .coverage import unavailable_coverage


def suite_plan(root):
    plan = json.loads((root / "cra-service/autograder/suite-plan.json").read_text())
    for name, expected in plan["source_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Suite plan is stale; regenerate it from collection")
    identifiers = plan["tests"]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("Invalid suite plan")
    return identifiers


def results_from_journal(planned, path, *, aborted=False):
    results = {
        identifier: {"test_id": identifier, "outcome": "skip", "message": "Test was not executed."}
        for identifier in planned
    }
    started, finished = set(), set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # A killed child may leave a partial final line.
            identifier = event.get("test_id")
            if identifier not in results:
                raise ValueError("Unplanned test in child journal")
            if event["event"] == "start":
                started.add(identifier)
            elif event["event"] == "result":
                results[identifier] = {
                    k: event[k] for k in ("test_id", "outcome", "message", "source") if k in event
                }
                finished.add(identifier)
    if aborted:
        for identifier in started - finished:
            results[identifier] = {
                "test_id": identifier,
                "outcome": "error",
                "source": "tester",
                "message": "Tester aborted before this test could be evaluated.",
            }
    return list(results.values()), finished == set(planned)


def report_body(target, identifier, results, *, message=None):
    report = {
        "session_id": identifier,
        "target_url": target,
        "results": results,
        "coverage": {
            k: v for k, v in unavailable_coverage().items() if k in {"code", "component", "system"}
        },
    }
    if message:
        report.update(aborted=True, message=redact_text(message), source="tester")
    return report
