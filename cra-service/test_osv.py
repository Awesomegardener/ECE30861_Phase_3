"""Independent synthetic OSV oracles; real upstream/SQL tests are separate."""

import copy
import datetime as dt
import hashlib
import json

import osv_source as osv
import pytest
from fastapi import HTTPException
from phase4 import require_reset_database, source_failures
from purl_matching import exact_purl


def record(**changes):
    return dict(id="CVE-2026-10001", modified="2026-11-01T00:00:00Z", **changes)


def envelope(records=None, **changes):
    value = dict(
        format="team2-osv-snapshot-v1",
        source_url="https://api.osv.dev/v1/vulns/CVE-2026-10001",
        fetched_at="2026-11-01T00:00:00Z",
        upstream_sha256="a" * 64,
        scope="synthetic-unit-test",
        records=records if records is not None else [record()],
    )
    value.update(changes)
    raw = json.dumps(value).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def test_official_schema_and_hash_validate_osv_not_fixture_format():
    raw, digest = envelope()
    bundle, fetched, actual = osv.validate_bundle(
        raw, digest, now=dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    )
    assert bundle["records"][0]["id"] == "CVE-2026-10001" and actual == digest
    assert fetched.hour == 0
    raw, digest = envelope([dict(cve_id="CVE-2026-10001", affected_purls=[])])
    with pytest.raises(ValueError, match="Invalid OSV"):
        osv.validate_bundle(raw, digest)


@pytest.mark.parametrize(
    "changes",
    [
        dict(format="fixture"),
        dict(source_url="http://api.osv.dev/v1/vulns/x"),
        dict(source_url="https://user:password@api.osv.dev/v1/vulns/x"),
        dict(source_url="https://api.osv.dev.evil.example/v1/vulns/x"),
        dict(fetched_at="2026-11-01T00:00:00"),
        dict(scope=""),
        dict(upstream_sha256="bad"),
        dict(records=[]),
        dict(records=[record(), record()]),
        dict(records=[record(schema_version="2.0.0")]),
        dict(records=[dict(id="CVE-2026-10001", modified="invalid")]),
        dict(fetched_at="2099-01-01T00:00:00Z"),
    ],
)
def test_invalid_snapshot_never_activates(changes):
    raw, digest = envelope(**changes)
    with pytest.raises(ValueError):
        osv.validate_bundle(raw, digest, now=dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc))


def test_snapshot_checksum_and_database_protection_before_writes():
    raw, digest = envelope()

    def forbidden(**kwargs):
        pytest.fail("Invalid import attempted a DB connection")

    with pytest.raises(ValueError, match="SHA-256"):
        osv.import_snapshot(forbidden, raw, "0" * 64, "cra_grading")
    with pytest.raises(ValueError, match="retained"):
        osv.import_snapshot(forbidden, raw, digest, "cra_phase3")


@pytest.mark.parametrize("name", ["cra_phase3", "cra_db", "postgres", "cra_grading", "cra_test"])
def test_legacy_reset_is_limited_to_disposable_databases(name):
    class Cursor:
        def execute(self, query):
            assert query == "SELECT current_database() AS name"

        def fetchone(self):
            return {"name": name}

    if name in {"cra_grading", "cra_test"}:
        require_reset_database(Cursor())
    else:
        with pytest.raises(HTTPException) as exc:
            require_reset_database(Cursor())
        assert exc.value.status_code == 503


@pytest.mark.parametrize(
    "purl,expected",
    [
        (None, None),
        ("abc", None),
        ("pkg:pypi/requests", None),
        ("pkg:pypi/requests@2.30.0?arch=x#folder/file", "pkg:pypi/requests@2.30.0"),
        ("pkg:generic/alpha@1#folder", "pkg:generic/alpha@1"),
    ],
)
def test_exact_fixture_identity(purl, expected):
    assert exact_purl(purl) == expected


@pytest.mark.parametrize(
    "version,expected",
    [
        ("0.9.9", False),
        ("1.0.0", True),
        ("1.9.9", True),
        ("2.0.0", False),
        ("2.5.0", False),
        ("3.0.0", True),
        ("3.0.1", True),
        ("3.0.2", False),
        ("1.0.0-alpha", False),
        ("1.0.0+build.1", True),
    ],
)
def test_semver_multiple_intervals_and_boundaries(version, expected):
    r = dict(
        type="SEMVER",
        events=[
            dict(introduced="3.0.0"),
            dict(fixed="3.0.2"),
            dict(introduced="1.0.0"),
            dict(fixed="2.0.0"),
        ],
    )
    assert osv.range_matches(version, r, "npm") == expected


@pytest.mark.parametrize("version,expected", [("2.0.0", True), ("2.1.0", True), ("2.1.1", False)])
def test_last_affected_is_inclusive(version, expected):
    assert (
        osv.range_matches(
            version,
            dict(type="SEMVER", events=[dict(introduced="0"), dict(last_affected="2.1.0")]),
            "npm",
        )
        == expected
    )


@pytest.mark.parametrize("version,expected", [("1.9.9", True), ("2.0.0", False), ("9.0.0", False)])
def test_limit_is_exclusive(version, expected):
    assert (
        osv.range_matches(
            version, dict(type="SEMVER", events=[dict(introduced="0"), dict(limit="2.0.0")]), "npm"
        )
        == expected
    )


@pytest.mark.parametrize(
    "version,expected",
    [("2.2.0", False), ("2.3.0", True), ("2.30.0", True), ("2.31.0", False), ("2.31.0rc1", True)],
)
def test_pypi_ecosystem_ordering(version, expected):
    assert (
        osv.range_matches(
            version,
            dict(type="ECOSYSTEM", events=[dict(introduced="2.3.0"), dict(fixed="2.31.0")]),
            "PyPI",
        )
        == expected
    )


@pytest.mark.parametrize(
    "kind,ecosystem,version",
    [("GIT", "PyPI", "abcdef"), ("ECOSYSTEM", "Maven", "1.0"), ("SEMVER", "npm", "invalid")],
)
def test_unsupported_comparisons_are_unavailable_not_negative(kind, ecosystem, version):
    with pytest.raises(osv.SourceUnavailable):
        osv.range_matches(version, dict(type=kind, events=[dict(introduced="0")]), ecosystem)


def test_osv_matches_package_version_qualifiers_and_not_withdrawn():
    r = record(
        affected=[dict(package=dict(ecosystem="PyPI", name="Requests"), versions=["2.30.0"])]
    )
    component = dict(
        name="requests", version="2.30.0", purl="pkg:pypi/requests@2.30.0?arch=x#folder"
    )
    assert osv.record_matches(r, component)
    for purl in (None, "pkg:pypi/requests@2.31.0", "pkg:pypi/other@2.30.0"):
        assert not osv.record_matches(r, {**component, "purl": purl})
    r["withdrawn"] = "2026-11-01T00:00:00Z"
    assert not osv.record_matches(r, component)


@pytest.mark.parametrize(
    "age,limit,ok",
    [
        (0, "60", True),
        (60, "60", True),
        (61, "60", False),
        (-301, "60", False),
        (0, "invalid", False),
        (0, "0", False),
    ],
)
def test_snapshot_freshness_uses_wall_clock(monkeypatch, age, limit, ok):
    now = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    monkeypatch.setenv("OSV_SNAPSHOT_MAX_AGE_SECONDS", limit)

    class Cursor:
        def execute(self, *args):
            pass

        def fetchone(self):
            return dict(snapshot_id="one", fetched_at=now - dt.timedelta(seconds=age))

        def fetchall(self):
            return [{"document": record()}]

    if ok:
        assert osv.read_records(Cursor(), "CVE-2026-10001", now=now) == [record()]
    else:
        with pytest.raises(osv.SourceUnavailable):
            osv.read_records(Cursor(), "CVE-2026-10001", now=now)


def test_uninitialized_snapshot_is_unavailable():
    class Cursor:
        def execute(self, *args):
            pass

        def fetchone(self):
            return None

    with pytest.raises(osv.SourceUnavailable, match="No OSV"):
        osv.read_records(Cursor(), "CVE-2026-10001")


def test_database_source_failure_is_503_and_redacted():
    import psycopg2

    @source_failures
    def unavailable():
        raise psycopg2.OperationalError("private-host password=do-not-expose")

    with pytest.raises(HTTPException) as exc:
        unavailable()
    assert exc.value.status_code == 503
    assert exc.value.detail == {
        "error": {
            "code": "VULNERABILITY_SOURCE_UNREACHABLE",
            "message": "Vulnerability storage is unavailable",
        }
    }


def test_versioned_package_and_unsupported_record_do_not_silently_hide_uncertainty():
    r = record(
        affected=[
            dict(
                package=dict(ecosystem="Maven", name="org.example:library"),
                ranges=[dict(type="ECOSYSTEM", events=[dict(introduced="0")])],
            )
        ]
    )
    component = dict(name="library", version="1.0", purl="pkg:maven/org.example/library@1.0")
    with pytest.raises(osv.SourceUnavailable):
        osv.records_match([r], component)
    supported = copy.deepcopy(r)
    supported["affected"][0]["versions"] = ["1.0"]
    assert osv.records_match([r, supported], component)
