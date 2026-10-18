"""Offline policy regressions; supported-version inputs use their real schemas."""

from collections import Counter
from copy import deepcopy

import pytest
from sbom_validation import InvalidSbom, validate_sbom


def test_supported_versions_flatten_inventory_without_changing_input(nested_sbom, nested_inventory):
    original = deepcopy(nested_sbom)
    components = validate_sbom(nested_sbom)
    actual = Counter((c["name"], c["version"], c.get("purl")) for c in components)
    expected = Counter((c["name"], c["version"], c.get("purl")) for c in nested_inventory)
    assert len(components) == 8 and actual == expected
    assert nested_sbom == original


@pytest.mark.parametrize(
    "version", ["1.0", "1.1", "1.2", "1.3", "1.7", "2.0", "1.6.0", "future", ""]
)
def test_unsupported_spec_versions_are_rejected(version):
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": version,
        "version": 1,
        "components": [{"type": "library", "name": "example", "version": "1"}],
    }
    with pytest.raises(InvalidSbom, match="supported versions: 1.4, 1.5, 1.6"):
        validate_sbom(document)


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_version_is_required_at_every_inventory_depth(nested_sbom, depth):
    component = nested_sbom["components"][0]
    if depth >= 1:
        component = component["components"][1]
    if depth == 2:
        component = component["components"][0]
    del component["version"]
    with pytest.raises(InvalidSbom, match="version"):
        validate_sbom(nested_sbom)


@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_nested_version_must_be_a_string(nested_sbom, value):
    nested_sbom["components"][0]["components"][1]["components"][0]["version"] = value
    with pytest.raises(InvalidSbom, match="version"):
        validate_sbom(nested_sbom)


@pytest.mark.parametrize("nested", [False, True], ids=["root", "nested"])
def test_identical_siblings_still_fail_cyclonedx_unique_items(nested_sbom, nested):
    siblings = nested_sbom["components"]
    if nested:
        siblings = siblings[0]["components"]
    siblings.append(deepcopy(siblings[0]))
    with pytest.raises(InvalidSbom, match="non-unique"):
        validate_sbom(nested_sbom)


def test_identical_occurrences_in_different_branches_are_retained(sbom_spec_version):
    leaf = {"type": "library", "name": "repeated", "version": "1"}
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": sbom_spec_version,
        "version": 1,
        "components": [
            {"type": "library", "name": name, "version": "1", "components": [deepcopy(leaf)]}
            for name in ["parent-a", "parent-b"]
        ],
    }
    components = validate_sbom(document)
    assert len(components) == 4
    assert sum(component["name"] == "repeated" for component in components) == 2


def test_declared_schema_is_used_instead_of_latest_schema():
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {"tools": {"components": [{"type": "application", "name": "tool"}]}},
        "components": [{"type": "library", "name": "example", "version": "1"}],
    }
    with pytest.raises(InvalidSbom, match="tools"):
        validate_sbom(document)


def test_excluded_metadata_is_still_schema_validated(nested_sbom):
    del nested_sbom["metadata"]["component"]["type"]
    with pytest.raises(InvalidSbom, match="type"):
        validate_sbom(nested_sbom)


def test_excluded_metadata_versions_follow_cyclonedx_not_inventory_requirements():
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "metadata-only"},
            "tools": {"components": [{"type": "application", "name": "tool-only"}]},
        },
        "components": [{"type": "library", "name": "inventory", "version": "1"}],
    }
    assert [component["name"] for component in validate_sbom(document)] == ["inventory"]


def test_flattening_handles_many_inventory_levels():
    component = {"type": "library", "name": "deepest", "version": "1"}
    for depth in range(30):
        component = {
            "type": "library",
            "name": f"level-{depth}",
            "version": "1",
            "components": [component],
        }
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [component],
    }
    components = validate_sbom(document)
    assert len(components) == 31
    assert any(component["name"] == "deepest" for component in components)
