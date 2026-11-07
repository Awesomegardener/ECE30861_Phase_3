"""Run the preserved Phase 3 and expanded Phase 4 suites in a bounded subprocess."""

import datetime
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from http_evidence import redact_text

SUITE_FILES = ("cra-service/test_api.py", "cra-service/test_phase4_api.py")
EXPECTED_TESTS = 353  # 157 original Phase 3 + 196 Phase 4 cases; checked against collection.
EXPECTED_MODULE_COUNTS = {"test_api": 157, "test_phase4_api": 196}
EXPECTED_PHASE4_AC_COUNTS = {"AC-04": 10, "AC-05": 11, "AC-06": 62, "AC-07": 113}
CHILDREN: set[subprocess.Popen] = set()
CHILD_LOCK = threading.Lock()


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def terminate(process):
    if process.poll() is not None:
        return
    if os.name == "posix":
        getattr(os, "killpg")(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            getattr(os, "killpg")(process.pid, getattr(signal, "SIGKILL"))
        else:
            process.kill()
        process.wait(timeout=2)


def shutdown_children():
    with CHILD_LOCK:
        children = list(CHILDREN)
    for child in children:
        terminate(child)


def empty_summary():
    return dict(
        required_passed=0,
        required_failed=0,
        informational_passed=0,
        informational_failed=0,
        passed=0,
        failed=0,
        errors=0,
        skipped=0,
        total=0,
    )


def acceptance_id(name):
    for number in range(4, 8):
        if name.startswith(f"test_ac{number:02d}"):
            return f"AC-{number:02d}"
    if name.startswith("test_ac02"):
        return "AC-02"
    if name.startswith("test_ac03"):
        return "AC-03"
    if "sbom" in name or "unknown_release" in name or "requires_nonempty_user" in name:
        return "AC-03"
    if "components" in name or "replacement" in name or "nested" in name or "ac02" in name:
        return "AC-02"
    return "AC-01"


def parse_junit(path, returncode, expected_count=EXPECTED_TESTS):
    root = ET.parse(path).getroot()
    checks, counts = [], empty_summary()
    for case in root.iter("testcase"):
        name = case.attrib["name"]
        failed, errors, skipped = (case.find(tag) for tag in ("failure", "error", "skipped"))
        outcome = (
            "error"
            if errors is not None
            else "fail"
            if failed is not None
            else "skip"
            if skipped is not None
            else "pass"
        )
        element = errors if errors is not None else failed if failed is not None else skipped
        detail = (
            "Assertions passed"
            if element is None
            else " ".join(filter(None, [element.get("message"), element.text]))
        )
        counts[
            {"error": "errors", "fail": "failed", "skip": "skipped", "pass": "passed"}[outcome]
        ] += 1
        checks.append(
            dict(
                id=f"{case.get('classname', '')}::{name}",
                ac=acceptance_id(name),
                title=name,
                required=True,
                passed=outcome == "pass",
                expected="All Phase 3 and Phase 4 pytest assertions pass",
                actual=redact_text(detail)[:12000],
                outcome=outcome,
                duration_seconds=float(case.get("time", "0")),
            )
        )
    counts.update(
        total=len(checks),
        required_passed=counts["passed"],
        required_failed=counts["failed"] + counts["errors"] + counts["skipped"],
    )
    suite_problem = None
    if expected_count == EXPECTED_TESTS:
        modules = Counter(c["id"].partition("::")[0].rsplit(".", 1)[-1] for c in checks)
        phase4_acs = Counter(c["ac"] for c in checks if c["ac"] in EXPECTED_PHASE4_AC_COUNTS)
        if len({c["id"] for c in checks}) != len(checks):
            suite_problem = "duplicate testcase identities"
        elif modules != EXPECTED_MODULE_COUNTS or phase4_acs != EXPECTED_PHASE4_AC_COUNTS:
            suite_problem = "required Phase 3/4 test files or acceptance groups are incomplete"
    error = None
    if (
        returncode not in {0, 1}
        or counts["errors"]
        or counts["skipped"]
        or len(checks) != expected_count
        or suite_problem is not None
    ):
        result = "error"
        error = f"pytest exit {returncode}; expected {expected_count} cases; observed {len(checks)} (including setup/teardown records)"
        if suite_problem:
            error += "; " + suite_problem
    elif counts["failed"]:
        result = "fail"
    elif returncode == 0:
        result = "pass"
    else:
        result, error = "error", "pytest failed without a recorded failing test"
    return dict(
        result=result, summary=counts, checks=checks, error=error, pytest_exit_code=returncode
    )


class Runner:
    def __init__(self, settings):
        self.settings = settings

    def aborted_report(self, target, identifier, message):
        from .reporting import report_body

        plan = json.loads(
            (self.settings.root / "cra-service/autograder/suite-plan.json").read_text()
        )["tests"]
        results = [
            {
                "test_id": test,
                "outcome": "skip",
                "message": "Test was not executed because the tester aborted.",
            }
            for test in plan
        ]
        return report_body(target, identifier, results, message=message)

    def execute_suite(self, target, identifier, deadline, heartbeat):
        from .client import TargetClient
        from .coverage import acceptance_coverage
        from .reporting import report_body, results_from_journal, suite_plan

        planned = suite_plan(self.settings.root)
        with tempfile.TemporaryDirectory(prefix="cra-cross-team-") as temporary:
            directory = Path(temporary)
            journal = directory / "results.jsonl"
            command = [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-m",
                "pytest",
                *SUITE_FILES,
                "-q",
                "-p",
                "no:cacheprovider",
                "-p",
                "autograder.pytest_guard",
                "--allow-reset",
                "--base-url",
                target,
                "--capture-http-bodies",
                "--evidence-dir",
                str(directory),
            ]
            environment = {
                k: v
                for k, v in os.environ.items()
                if not any(
                    term in k.upper()
                    for term in ("DATABASE", "PASSWORD", "SECRET", "TOKEN", "CREDENTIAL")
                )
            }
            for key in ("PYTEST_ADDOPTS", "TESTED_COMMIT_SHA"):
                environment.pop(key, None)
            environment.update(
                PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONPATH=str(self.settings.root / "cra-service"),
                CRA_HARNESS_TARGET=target,
                CRA_HARNESS_SESSION_ID=identifier,
                CRA_HARNESS_JOURNAL=str(journal),
            )
            message = None
            process = None
            try:
                with (directory / "pytest.log").open("w") as output:
                    process = subprocess.Popen(
                        command,
                        cwd=self.settings.root,
                        env=environment,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=os.name == "posix",
                    )
                    with CHILD_LOCK:
                        CHILDREN.add(process)
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "Tester run exceeded its registered total time limit"
                            )
                        heartbeat()
                        try:
                            process.wait(timeout=min(0.1, max(0.01, deadline - time.monotonic())))
                        except subprocess.TimeoutExpired:
                            pass
                if process.returncode not in {0, 1}:
                    message = "Tester process aborted before completing the planned suite"
            except TimeoutError as exc:
                message = str(exc)
            except Exception:
                message = "Tester execution was interrupted"
            finally:
                if process is not None:
                    terminate(process)
                    with CHILD_LOCK:
                        CHILDREN.discard(process)
            results, complete = results_from_journal(planned, journal, aborted=True)
            if not complete and not message:
                message = "Tester did not produce every planned result"
            body = report_body(target, identifier, results, message=message)
            evidence = next(directory.glob("http-evidence-*.json"), None)
            if evidence:
                try:
                    bundle = json.loads(evidence.read_text())
                    body["coverage"]["system"] = acceptance_coverage(bundle["exchanges"])
                except (ValueError, KeyError, TypeError):
                    # Preserve the independent result journal on evidence failure.
                    message = message or "Tester could not assemble scenario coverage evidence"
                    body.update(aborted=True, message=message, source="tester")
            body["coverage"]["code"] = TargetClient(self.settings, target).code_coverage(
                identifier, deadline
            )
            return body, bool(message)
