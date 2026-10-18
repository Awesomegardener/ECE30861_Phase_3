"""Validate supported CycloneDX schemas offline, then flatten inventory only."""

import json
from typing import Any

from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator, JsonValidationError


class InvalidSbom(ValueError):
    """A document cannot be safely normalized into the component API."""


SUPPORTED_SPEC_VERSIONS = ("1.4", "1.5", "1.6")


VALIDATORS = {
    version.to_version(): JsonStrictValidator(version)
    for version in SchemaVersion
    if version.to_version() in SUPPORTED_SPEC_VERSIONS
}


def validate_sbom(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        raise InvalidSbom("The CycloneDX document must be a JSON object")
    version = document.get("specVersion")
    if not isinstance(version, str):
        raise InvalidSbom("specVersion is required and must be a string")
    validator = VALIDATORS.get(version)
    if validator is None:
        raise InvalidSbom(
            f"Unsupported CycloneDX specVersion {version!r}; "
            f"supported versions: {', '.join(SUPPORTED_SPEC_VERSIONS)}"
        )
    try:
        serialized = json.dumps(document, allow_nan=False)
    except ValueError as exc:
        raise InvalidSbom("The SBOM contains a non-JSON numeric value") from exc
    error = validator.validate_str(serialized)
    if isinstance(error, JsonValidationError):
        location = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.data.absolute_path
        )
        raise InvalidSbom(f"{location}: {error.data.message}")

    # Validate the whole document before normalization, including excluded metadata.
    # Traverse only the inventory tree; metadata/component and metadata/tools are
    # not inventory. Preserve occurrences rather than deduplicating name/version.
    components = document.get("components")
    if not isinstance(components, list):
        raise InvalidSbom("components must be an array")
    flattened = []
    pending = [
        (component, f"components[{index}]")
        for index, component in reversed(list(enumerate(components)))
    ]
    while pending:
        component, path = pending.pop()
        if not isinstance(component.get("version"), str):
            raise InvalidSbom(f"{path}.version is required and must be a string")
        flattened.append(component)
        pending.extend(
            (child, f"{path}.components[{index}]")
            for index, child in reversed(list(enumerate(component.get("components", []))))
        )
    return flattened
