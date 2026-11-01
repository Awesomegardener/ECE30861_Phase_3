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
from typing import Any

from http_evidence import redact_text

from .config import TEAM2, HarnessError

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

    def execute(self, target, heartbeat):
        target = self.settings.authorize(target)
        verify_public_target(target)
        with tempfile.TemporaryDirectory(prefix="cra-acceptance-") as temporary:
            directory = Path(temporary)
            xml = directory / "results.xml"
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
                "--junitxml",
                str(xml),
            ]
            environment = os.environ.copy()
            # The child needs HTTP access only: do not inherit database secrets.
            for key in list(environment):
                if any(
                    term in key.upper()
                    for term in ("DATABASE", "PASSWORD", "SECRET", "TOKEN", "CREDENTIAL")
                ):
                    environment.pop(key)
            environment.pop("PYTEST_ADDOPTS", None)
            environment.pop("TESTED_COMMIT_SHA", None)
            environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
            environment["PYTHONPATH"] = str(self.settings.root / "cra-service")
            environment["CRA_HARNESS_TARGET"] = target
            with (directory / "pytest.log").open("w", encoding="utf-8") as output:
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
                try:
                    deadline = time.monotonic() + self.settings.timeout
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Acceptance suite exceeded its subprocess timeout")
                        heartbeat()
                        try:
                            process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    terminate(process)
                    with CHILD_LOCK:
                        CHILDREN.discard(process)
            result = parse_junit(xml, process.returncode)
            result["runner_build_sha"] = os.getenv("BUILD_SHA") or None
            result["tested_commit_sha"] = None  # No claim about a remote target's deployed SHA.
            # Keep real redacted HTTP examples with test ids/statuses/UTC times.
            evidence = next(directory.glob("http-evidence-*.json"), None)
            if evidence:
                bundle = json.loads(evidence.read_text(encoding="utf-8"))
                result["evidence"] = dict(run=bundle["run"], exchanges=bundle["exchanges"][:8])
                examples: dict[tuple[str, str], Any] = {}
                for exchange in bundle["exchanges"]:
                    node_id = exchange.get("test_id") or ""
                    file, _, name = node_id.partition("::")
                    # Minimal Docker images and host pytest select different roots.
                    examples[(file.replace("\\", "/").rsplit("/", 1)[-1], name)] = exchange
                for check in result["checks"]:
                    module = check["id"].partition("::")[0].rsplit(".", 1)[-1]
                    example = examples.get((module + ".py", check["title"]))
                    if example:
                        check["request"] = json.dumps(example["request"])[:3000]
                        check["response"] = json.dumps(
                            dict(status=example["status"], response=example["response"])
                        )[:3000]
            return result


def verify_public_target(target):
    """Do not send legacy reset calls to our public URL before its DB migration.

    This Team 2-only readiness signal is not imposed on Team 6's independent
    interface. Their approved target still requires a coordinated reset window.
    """
    if target != TEAM2:
        return
    import requests  # type: ignore[import-untyped]

    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(target + "/test", timeout=5, allow_redirects=False)
        data = response.json() if response.status_code == 200 else None
    except (requests.RequestException, ValueError):
        data = None
    if (
        not isinstance(data, dict)
        or data.get("role") != "system"
        or data.get("reset_ready") is not True
    ):
        raise HarnessError(
            503,
            "RESET_DISABLED",
            "Team 2 public target is not ready for guarded grading resets; verify its grading revision first",
        )
