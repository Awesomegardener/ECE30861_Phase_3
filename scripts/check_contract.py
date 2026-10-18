"""Validate authoritative inputs and emit observations for every shared operation."""

import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import yaml
from openapi_spec_validator import validate_spec

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = yaml.safe_load((ROOT / "docs/openapi.yaml").read_text(encoding="utf-8"))
    validate_spec(spec)
    sys.path.insert(0, str(ROOT / "cra-service"))
    from sbom_validation import validate_sbom

    bom = json.loads((ROOT / "fixtures/sbom_25_components.json").read_text(encoding="utf-8"))
    components = validate_sbom(bom)
    pairs = Counter((c["name"], c["version"]) for c in components)
    locked = Counter(
        tuple(line.split("=="))
        for line in (ROOT / "fixtures/sbom_source/requirements.txt").read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert len(components) == 25 and len(pairs) == 25 and pairs == locked
    source = ast.parse((ROOT / "cra-service/main.py").read_text(encoding="utf-8-sig"))
    methods = {"get", "post", "put", "patch", "delete"}
    implemented = set()
    for node in source.body:
        for decorator in getattr(node, "decorator_list", []):
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.func.attr in methods
            ):
                implemented.add((decorator.func.attr, decorator.args[0].value))
    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    observations_file = artifact_dir / "operation-observations.json"
    observations = json.loads(observations_file.read_text()) if observations_file.exists() else []
    status = []
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in methods:
                continue
            seen = [
                entry
                for entry in observations
                if entry["method"].lower() == method and entry["path"] == path
            ]
            status.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "requirements": operation.get("x-requirements", []),
                    "route_present": (method, path) in implemented,
                    "contract_statuses": sorted(operation["responses"]),
                    "observed_statuses": sorted({entry["status"] for entry in seen}),
                    "undocumented_observed_statuses": sorted(
                        {entry["status"] for entry in seen if not entry["documented"]}
                    ),
                }
            )
    (artifact_dir / "operation-status.json").write_text(
        json.dumps(status, indent=2), encoding="utf-8"
    )
    protected = [ROOT / "docs/openapi.yaml", *sorted((ROOT / "fixtures").rglob("*"))]
    hashes = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in protected
        if path.is_file()
    }
    (artifact_dir / "protected-inputs.sha256.json").write_text(
        json.dumps(hashes, indent=2), encoding="utf-8"
    )
    print(
        f"OpenAPI 3.1 valid; shared fixture matches all 25 locked packages; {len(status)} operations reported."
    )


if __name__ == "__main__":
    main()
