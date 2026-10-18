"""Offline validation using the schema selected by the document's specVersion."""

import json
from typing import Any

from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator, JsonValidationError


class InvalidSbom(ValueError):
    """A document cannot be safely normalized into the component API."""


def _validators() -> dict[str, JsonStrictValidator]:
    result = {}
    for version in SchemaVersion:
        try:
            result[version.to_version()] = JsonStrictValidator(version)
        except ValueError:
            # CycloneDX 1.0/1.1 do not have packaged JSON schemas.
            continue
    return result


VALIDATORS = _validators()


def validate_sbom(document: Any) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        raise InvalidSbom("The CycloneDX document must be a JSON object")
    version = document.get("specVersion")
    if not isinstance(version, str):
        raise InvalidSbom("specVersion is required and must be a string")
    validator = VALIDATORS.get(version)
    if validator is None:
        raise InvalidSbom(f"No packaged CycloneDX JSON schema for specVersion {version!r}")
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

    # Preserve existing normalization until open pod policies are resolved.
    # The schema has already checked nested content, including tool metadata.
    components = document.get("components")
    if not isinstance(components, list):
        raise InvalidSbom("components must be an array")
    for index, component in enumerate(components):
        if not isinstance(component.get("version"), str):
            raise InvalidSbom(f"components[{index}].version is required and must be a string")
    return components
