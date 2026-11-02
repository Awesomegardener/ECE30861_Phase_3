"""Offline OSV snapshots: validated atomic ingestion, provenance and local matching.

Fixtures are a different source. HTTP lookups never download upstream data and
never fall back to an empty/fixture result on a stale or unsupported snapshot.
"""

import datetime as dt
import hashlib
import json
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import semver
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from packageurl import PackageURL
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from psycopg2.extras import Json
from purl_matching import package_key, parse_purl

UTC = dt.timezone.utc
CVE_PATTERN = r"CVE-[0-9]{4}-[0-9]+"
SCHEMA_ROOT = Path(__file__).parent / "vendor/osv"
SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS osv_snapshots (
        snapshot_id TEXT PRIMARY KEY, source_url TEXT NOT NULL,
        scope TEXT NOT NULL, content_sha256 TEXT NOT NULL,
        upstream_sha256 TEXT NOT NULL, schema_sha256 TEXT NOT NULL,
        fetched_at TIMESTAMPTZ NOT NULL, imported_at TIMESTAMPTZ NOT NULL,
        record_count INTEGER NOT NULL CHECK(record_count>=0)
    )""",
    """CREATE TABLE IF NOT EXISTS osv_records (
        snapshot_id TEXT NOT NULL REFERENCES osv_snapshots(snapshot_id),
        record_id TEXT NOT NULL, document JSONB NOT NULL,
        PRIMARY KEY(snapshot_id, record_id)
    )""",
    """CREATE TABLE IF NOT EXISTS osv_cves (
        snapshot_id TEXT NOT NULL, cve_id TEXT NOT NULL, record_id TEXT NOT NULL,
        PRIMARY KEY(snapshot_id,cve_id,record_id),
        FOREIGN KEY(snapshot_id,record_id) REFERENCES osv_records(snapshot_id,record_id)
    )""",
    """CREATE TABLE IF NOT EXISTS osv_active (
        id INTEGER PRIMARY KEY CHECK(id=1),
        snapshot_id TEXT NOT NULL REFERENCES osv_snapshots(snapshot_id)
    )""",
)


class SourceUnavailable(ValueError):
    pass


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("Snapshot timestamp must be a timezone-aware string")
    value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Snapshot timestamp requires a timezone")
    return value.astimezone(UTC)


@lru_cache
def record_validator():
    provenance = json.loads((SCHEMA_ROOT / "SOURCE.json").read_text(encoding="utf8"))
    raw = (SCHEMA_ROOT / "schema.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance["schema_sha256"]:
        raise ValueError("Pinned OSV validation schema checksum mismatch")
    return Draft202012Validator(json.loads(raw), format_checker=FormatChecker())


def source_url_allowed(value):
    if not isinstance(value, str):
        return False
    try:
        p = urlsplit(value)
        port = p.port
    except ValueError:
        return False
    return (
        p.scheme == "https"
        and p.username is None
        and p.password is None
        and not p.query
        and not p.fragment
        and port is None
        and (
            (p.hostname == "api.osv.dev" and p.path.startswith("/v1/vulns/"))
            or (
                p.hostname == "storage.googleapis.com"
                and p.path.startswith("/osv-vulnerabilities/")
            )
        )
    )


def validate_bundle(raw, expected_sha256, *, now=None):
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Snapshot file SHA-256 does not match the approved hash")
    if len(raw) > 256 * 1024 * 1024:
        raise ValueError("Snapshot exceeds 256 MiB limit")
    bundle = json.loads(raw)
    if not isinstance(bundle, dict):
        raise ValueError("Snapshot must be a JSON object")
    if bundle.get("format") != "team2-osv-snapshot-v1" or not source_url_allowed(
        bundle.get("source_url")
    ):
        raise ValueError("Snapshot requires an official OSV source URL and supported bundle format")
    if not isinstance(bundle.get("scope"), str) or not bundle["scope"].strip():
        raise ValueError("Snapshot coverage scope must be recorded")
    if not re.fullmatch(r"[0-9a-f]{64}", bundle.get("upstream_sha256", "")):
        raise ValueError("Snapshot requires the downloaded artifact hash")
    fetched = parse_time(bundle.get("fetched_at"))
    now = now or dt.datetime.now(UTC)
    if fetched > now + dt.timedelta(minutes=5):
        raise ValueError("Snapshot fetch time is in the future")
    records = bundle.get("records")
    if not isinstance(records, list) or not records or len(records) > 50000:
        raise ValueError("Snapshot requires 1..50000 OSV records")
    seen = set()
    for record in records:
        try:
            record_validator().validate(record)
        except ValidationError as exc:
            raise ValueError("Invalid OSV record at " + ".".join(map(str, exc.path))) from None
        identifier = record["id"]
        if identifier in seen:
            raise ValueError("Duplicate OSV record ID; assemble one consistent snapshot")
        seen.add(identifier)
        if semver.Version.parse(record.get("schema_version", "1.0.0")).major != 1:
            raise ValueError("Unsupported OSV schema major version")
        for affected in record.get("affected", []):
            for version_range in affected.get("ranges", []):
                events = version_range["events"]
                if not any("introduced" in e for e in events):
                    raise ValueError("OSV range requires an introduced event")
                if any("fixed" in e for e in events) and any("last_affected" in e for e in events):
                    raise ValueError("OSV range cannot mix fixed and last_affected")
                # The schema validates shape; actual ordering is source-specific.
                if version_range["type"] == "SEMVER":
                    for e in events:
                        for key, value in e.items():
                            if not (key == "introduced" and value == "0") and not (
                                key == "limit" and value == "*"
                            ):
                                semver.Version.parse(value)
    return bundle, fetched, digest


def import_snapshot(database, raw, expected_sha256, expected_database, *, now=None):
    # Validate all input before any database write. Provenance is operator-attested
    # for offline files; the fetch command also verifies HTTPS origin/no redirects.
    bundle, fetched, digest = validate_bundle(raw, expected_sha256, now=now)
    if expected_database in {"cra_phase3", "postgres", "template0", "template1", ""}:
        raise ValueError("Refusing snapshot import into a retained/system database")
    identifier = "osv-" + uuid.uuid4().hex
    schema_sha = json.loads((SCHEMA_ROOT / "SOURCE.json").read_text())["schema_sha256"]
    with database(statement_timeout_ms=30000, lock_timeout_ms=3000) as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database() AS name")
        if cur.fetchone()["name"] != expected_database:
            raise ValueError("Actual database does not match explicit import approval")
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (30861004,))
        cur.execute(
            "INSERT INTO osv_snapshots VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                identifier,
                bundle["source_url"],
                bundle["scope"],
                digest,
                bundle["upstream_sha256"],
                schema_sha,
                fetched,
                dt.datetime.now(UTC),
                len(bundle["records"]),
            ),
        )
        for record in bundle["records"]:
            cur.execute(
                "INSERT INTO osv_records VALUES (%s,%s,%s)",
                (identifier, record["id"], Json(record)),
            )
            cves = {
                c
                for c in [record["id"], *(record.get("aliases") or [])]
                if re.fullmatch(CVE_PATTERN, c)
            }
            cur.executemany(
                "INSERT INTO osv_cves VALUES (%s,%s,%s)",
                [(identifier, cve, record["id"]) for cve in sorted(cves)],
            )
        cur.execute(
            "INSERT INTO osv_active VALUES (1,%s) ON CONFLICT(id) DO UPDATE SET snapshot_id=EXCLUDED.snapshot_id",
            (identifier,),
        )
    return dict(
        snapshot_id=identifier,
        sha256=digest,
        record_count=len(bundle["records"]),
        scope=bundle["scope"],
        fetched_at=fetched.isoformat(),
    )


def read_records(cur, cve_id, *, now=None):
    cur.execute("SELECT s.* FROM osv_active a JOIN osv_snapshots s USING(snapshot_id) WHERE a.id=1")
    snapshot = cur.fetchone()
    if not snapshot:
        raise SourceUnavailable("No OSV snapshot has been imported")
    try:
        max_age = int(os.getenv("OSV_SNAPSHOT_MAX_AGE_SECONDS", "604800"))
        now = now or dt.datetime.now(UTC)  # Wall clock, never the injectable incident clock.
        age = (now - snapshot["fetched_at"]).total_seconds()
        if max_age < 1 or max_age > 7776000 or age < -300 or age > max_age:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise SourceUnavailable(
            "OSV snapshot is stale or freshness configuration is invalid"
        ) from None
    cur.execute(
        "SELECT r.document FROM osv_cves c JOIN osv_records r USING(snapshot_id,record_id) WHERE c.snapshot_id=%s AND c.cve_id=%s ORDER BY r.record_id",
        (snapshot["snapshot_id"], cve_id),
    )
    return [row["document"] for row in cur.fetchall()]


def affected_package(package):
    if not package:
        return None
    if package.get("purl"):
        return parse_purl(package["purl"])
    ecosystem, name = package.get("ecosystem"), package.get("name")
    types = {
        "PyPI": "pypi",
        "npm": "npm",
        "Maven": "maven",
        "Go": "golang",
        "crates.io": "cargo",
        "NuGet": "nuget",
    }
    if ecosystem not in types or not name:
        return None
    try:
        if ecosystem == "PyPI":
            return PackageURL(type="pypi", name=canonicalize_name(name))
        if ecosystem == "Maven":
            namespace, separator, name = name.partition(":")
            return PackageURL(type="maven", namespace=namespace, name=name) if separator else None
    except ValueError:
        return None  # Unmappable upstream packages are unavailable, never guessed.
    return parse_purl("pkg:" + types[ecosystem] + "/" + name)


def range_matches(version, version_range, ecosystem):
    kind = version_range["type"]
    parser: Callable[[str], Any]
    if kind == "SEMVER":
        parser = semver.Version.parse
    elif kind == "ECOSYSTEM" and ecosystem == "PyPI":
        parser = Version
    else:
        raise SourceUnavailable("OSV range type/ecosystem is not supported by this matcher")
    try:
        candidate = parser(version)
        events = version_range["events"]
        limits = [e["limit"] for e in events if "limit" in e]
        if limits and not any(limit == "*" or candidate < parser(limit) for limit in limits):
            return False
        changes = []
        for e in events:
            for key, value in e.items():
                if key != "limit":
                    changes.append(
                        (None if key == "introduced" and value == "0" else parser(value), key)
                    )
        changes.sort(key=lambda pair: (pair[0] is not None, pair[0]))
        vulnerable = False
        for boundary, key in changes:
            if boundary is None or candidate >= boundary:
                if key == "introduced":
                    vulnerable = True
                elif key == "fixed" or (
                    key == "last_affected" and boundary is not None and candidate > boundary
                ):
                    vulnerable = False
        return vulnerable
    except (ValueError, TypeError, InvalidVersion):
        raise SourceUnavailable("OSV package version/range cannot be compared safely") from None


def record_matches(record, component):
    parsed = parse_purl(component.get("purl"))
    if not parsed or not parsed.version or record.get("withdrawn"):
        return False
    uncertain = False
    for entry in record.get("affected", []):
        package = entry.get("package")
        affected = affected_package(package)
        if affected is None:
            uncertain = True
            continue
        if package_key(affected) != package_key(parsed):
            continue
        if parsed.version in entry.get("versions", []):
            return True
        for version_range in entry.get("ranges", []):
            try:
                if range_matches(parsed.version, version_range, (package or {}).get("ecosystem")):
                    return True
            except SourceUnavailable:
                uncertain = True
    if uncertain:
        raise SourceUnavailable("OSV record has unsupported matching details for this inventory")
    return False


def records_match(records, component):
    uncertain = None
    for record in records:
        try:
            if record_matches(record, component):
                return True
        except SourceUnavailable as exc:
            uncertain = exc
    if uncertain:
        raise uncertain
    return False
