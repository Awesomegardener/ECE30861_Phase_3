"""Collect, without executing, the planned tests needed for complete abort reports."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["cra-service/test_api.py", "cra-service/test_phase4_api.py", "cra-service/conftest.py"]
PLAN = ROOT / "cra-service/autograder/suite-plan.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    environment = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *SOURCES[:2],
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    tests = [
        line.strip()
        for line in result.stdout.splitlines()
        if any(line.startswith(name + "::") for name in SOURCES[:2])
    ]
    if len(tests) != 353 or len(set(tests)) != len(tests):
        raise ValueError("Expected 353 unique preserved Phase 3/4 tests")
    plan = {
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES
        },
        "tests": tests,
    }
    if args.check:
        if plan != json.loads(PLAN.read_text()):
            raise ValueError("Suite plan is stale: run python scripts/update_suite_plan.py")
    else:
        PLAN.write_text(json.dumps(plan, indent=2) + "\n")
    print(
        "Suite plan matches collection: 353 tests"
        if args.check
        else "Updated suite plan: 353 tests"
    )


if __name__ == "__main__":
    main()
