"""Pod PURL identity: ignore qualifiers/subpath, retain the exact version."""

from packageurl import PackageURL


def parse_purl(value):
    if not isinstance(value, str):
        return None
    try:
        return PackageURL.from_string(value.split("#", 1)[0].split("?", 1)[0])
    except (ValueError, TypeError):
        return None


def exact_purl(value):
    parsed = parse_purl(value)
    if parsed is None or not parsed.version:
        return None
    # Retain the exact identity spelling; no additional case/version equivalence
    # is imposed on the pod's deterministic affected_purls strings.
    return value.split("#", 1)[0].split("?", 1)[0]


def package_key(parsed):
    return (parsed.type, parsed.namespace or "", parsed.name)
