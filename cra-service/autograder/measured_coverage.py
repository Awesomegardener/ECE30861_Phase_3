"""Proposed measures from server traces plus named behavioral assertions.

Consumed only by the isolated evidence workflow, never inferred for remote peers.
"""

import ast
import bisect
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_ranges(path):
    result: dict[str, set[int]] = {}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                assert child.end_lineno is not None
                result[name] = set(range(child.body[0].lineno, child.end_lineno + 1))
                walk(child, name + ".")
            else:
                walk(child, prefix)

    walk(ast.parse(path.read_text()))
    return result


def check_identity(check):
    module = check["id"].partition("::")[0].rsplit(".", 1)[-1]
    return module + "::" + check["title"]


def logical_contexts(data):
    """Coverage JSON uses logical statement lines but physical context lines.

    Continuation lines belong to the preceding logical executable statement;
    keep the original physical trace unchanged in the persisted artifact.
    """
    statements = sorted(
        set(data["executed_lines"])
        | set(data["missing_lines"])
        | set(data.get("excluded_lines", []))
    )
    result: dict[int, set[str]] = {}
    for physical, contexts in data.get("contexts", {}).items():
        index = bisect.bisect_right(statements, int(physical)) - 1
        if index >= 0:
            result.setdefault(statements[index], set()).update(contexts)
    return result


def measured_coverage(root, directory, report):
    metadata = json.loads((directory / "metadata.json").read_text())
    raw_path = directory / "server-coverage.json"
    raw = json.loads(raw_path.read_text())
    definition_path = root / "docs/coverage-model.json"
    model = json.loads(definition_path.read_text())
    if metadata.get("session_id", metadata["run_id"]) != report["session_id"]:
        raise ValueError("Coverage belongs to another session")
    if "role" in metadata and metadata["role"] != report.get("role"):
        raise ValueError("Coverage belongs to another role")
    if raw["meta"]["version"] != metadata["coverage_version"] or not raw["meta"]["branch_coverage"]:
        raise ValueError("Coverage metadata mismatch")
    expected_files = {"cra-service/" + name for name in model["source_files"]}
    if set(metadata["source_sha256"]) != expected_files:
        raise ValueError("Incomplete server-source denominator")
    if set(metadata["test_sha256"]) != {
        "cra-service/test_api.py",
        "cra-service/test_phase4_api.py",
    }:
        raise ValueError("Incomplete test-source provenance")
    for name, expected in {**metadata["source_sha256"], **metadata["test_sha256"]}.items():
        if digest(root / name) != expected:
            raise ValueError("Server/test source differs from measured revision: " + name)
    files = {Path(name).name: data for name, data in raw["files"].items()}
    if set(files) != set(model["source_files"]):
        raise ValueError("Coverage omitted a source file, including possibly zero-hit files")
    checks = {check_identity(check): check for check in report["checks"]}
    trace: dict[str, dict[str, set[int]]] = {}
    prefix = metadata["run_id"] + "|cra-service/"
    for name, data in files.items():
        attributed_lines = set()
        for line, contexts in logical_contexts(data).items():
            if line not in data["executed_lines"]:
                continue
            for context in contexts:
                if context.startswith(prefix):
                    identity = context[len(prefix) :].replace(".py::", "::", 1)
                    if identity not in checks:
                        raise ValueError("Coverage contains an uncollected test context")
                    trace.setdefault(identity, {}).setdefault(name, set()).add(int(line))
                    attributed_lines.add(int(line))
        if attributed_lines != set(data["executed_lines"]):
            raise ValueError("Executed statement has no matching test context")
    if not trace:
        raise ValueError("No attributed server execution from collected HTTP tests")
    provenance = {
        **metadata,
        "definition_version": model["version"],
        "definition_sha256": digest(definition_path),
        "trace_sha256": digest(raw_path),
        "proposed_measure": True,
        "attributed_tests": len(trace),
        "limitation": "Serialized isolated server; excludes startup, health and harness traffic",
    }
    line_total = sum(data["summary"]["num_statements"] for data in files.values())
    line_covered = sum(len(data["executed_lines"]) for data in files.values())
    if line_total <= 0:
        raise ValueError("Empty source statement denominator")
    branch_total = sum(data["summary"]["num_branches"] for data in files.values())
    branch_covered = sum(data["summary"]["covered_branches"] for data in files.values())
    code = {
        "status": "measured",
        "metric": "executed Python statements / executable statements",
        "covered": line_covered,
        "total": line_total,
        "percent": round(100 * line_covered / line_total, 2),
        "branches": {
            "covered": branch_covered,
            "total": branch_total,
            "percent": round(100 * branch_covered / branch_total, 2) if branch_total else None,
        },
        "files": {
            name: {"summary": data["summary"], "missing_lines": data["missing_lines"]}
            for name, data in files.items()
        },
        "provenance": provenance,
    }
    ranges = {name: function_ranges(root / "cra-service" / name) for name in files}
    components = []
    hits: dict[str, set[str]] = {}
    for component in model["components"]:
        tests = set()
        for name, functions in component["functions"].items():
            for function in functions:
                if function not in ranges[name]:
                    raise ValueError("Component mapping refers to missing function: " + function)
                for identity, execution in trace.items():
                    if ranges[name][function] & execution.get(name, set()):
                        tests.add(identity)
        hits[component["id"]] = tests
        components.append({**component, "exercised": bool(tests), "tests": sorted(tests)})
    transitions = []
    for transition in model["transitions"]:
        selector = transition["test"]
        witnesses = []
        for identity, check in checks.items():
            if not selector or not check["passed"]:
                continue
            if identity != selector and not identity.startswith(selector + "["):
                continue
            if transition.get("parameter_contains", "") not in identity:
                continue
            if all(identity in hits[c] for c in transition["components"]):
                witnesses.append(identity)
        transitions.append({**transition, "exercised": bool(witnesses), "tests": sorted(witnesses)})

    def metric(items, definition):
        covered = sum(item["exercised"] for item in items)
        return {
            "status": "measured",
            "metric": definition,
            "covered": covered,
            "total": len(items),
            "percent": round(100 * covered / len(items), 2),
            "items": items,
            "definition_version": model["version"],
            "definition_sha256": provenance["definition_sha256"],
            "proposed_measure": True,
        }

    return {
        "code": code,
        "component": metric(
            components,
            "architectural components with attributed function-body execution / defined components",
        ),
        "system": metric(
            transitions,
            "named domain transitions with passing behavioral assertions and required server execution / defined transitions",
        ),
    }
