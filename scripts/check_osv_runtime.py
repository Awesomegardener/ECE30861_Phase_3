"""Exercise real OSV ingestion/matching only in a fresh local OSV test database."""

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--base-url", default="http://127.0.0.1:18094")
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "artifacts/osv")
    parser.add_argument("--real-snapshot", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"cra-phase3-autograder-[a-z0-9-]+", args.project) or not re.fullmatch(
        r"http://127\.0\.0\.1:[0-9]+", args.base_url
    ):
        raise ValueError("Only a fresh isolated local harness project is allowed")
    prefix = [
        args.docker,
        "compose",
        "-p",
        args.project,
        "-f",
        str(ROOT / "tester-service/docker-compose.test.yml"),
    ]

    def run(command, *, raw=None, success=True):
        result = subprocess.run(command, input=raw, capture_output=True, timeout=60)
        if success and result.returncode:
            raise AssertionError(result.stdout.decode() + result.stderr.decode())
        return result

    container = run(prefix + ["ps", "-q", "osv"]).stdout.decode().strip()
    config = json.loads(run([args.docker, "inspect", container]).stdout)[0]
    assert config["Config"]["Labels"]["com.docker.compose.project"] == args.project
    environment = dict(s.split("=", 1) for s in config["Config"]["Env"] if "=" in s)
    assert environment["DATABASE_URL"] == "postgresql://cra_osv_app:local_osv_only@db:5432/cra_osv"
    assert environment["VULNERABILITY_SOURCE"] == "osv"
    port = config["NetworkSettings"]["Ports"]["8080/tcp"][0]
    assert port["HostIp"] == "127.0.0.1" and args.base_url == "http://127.0.0.1:" + port["HostPort"]
    observations, checks = [], []

    def call(method, path, expected=200, **kwargs):
        response = requests.request(
            method,
            args.base_url + "/api/v1" + path,
            headers={"X-User-Id": "osv-runtime"},
            timeout=10,
            **kwargs,
        )
        assert response.status_code == expected, response.text
        body = response.json()
        observations.append(
            dict(
                method=method,
                path=path,
                status=response.status_code,
                body=body,
                utc=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
        return body

    def inspect():
        return json.loads(
            run(
                prefix + ["exec", "-T", "osv", "python", "/app/scripts/osv_snapshot.py", "inspect"]
            ).stdout
        )

    def sql(statement):
        program = "import sys,main\nwith main.database() as conn,conn.cursor() as cur:\n cur.execute(sys.argv[1])\n"
        run(prefix + ["exec", "-T", "osv", "python", "-c", program, statement])

    def import_raw(raw, *, bad_hash=False, success=True):
        digest = hashlib.sha256(raw).hexdigest()
        program = """import sys,subprocess,uuid
from pathlib import Path
path=Path('/tmp/osv-runtime-'+uuid.uuid4().hex+'.json')
path.write_bytes(sys.stdin.buffer.read())
raise SystemExit(subprocess.call([sys.executable,'/app/scripts/osv_snapshot.py','import','--snapshot',str(path),'--sha256',sys.argv[1],'--database-name','cra_osv','--allow-import']))
"""
        return run(
            prefix
            + ["exec", "-T", "osv", "python", "-c", program, "0" * 64 if bad_hash else digest],
            raw=raw,
            success=success,
        )

    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    def bundle(records):
        return json.dumps(
            dict(
                format="team2-osv-snapshot-v1",
                source_url="https://api.osv.dev/v1/vulns/CVE-2026-10001",
                fetched_at=now,
                scope="synthetic-integration",
                upstream_sha256="a" * 64,
                records=records,
            )
        ).encode()

    def rec(cve, **extra):
        return dict(id=cve, modified="2026-11-01T00:00:00Z", **extra)

    assert inspect() is None, "Run only against a newly created empty OSV database"
    call("GET", "/vulnerabilities/CVE-2026-10001/affected-releases", 503)
    ids = []
    for version in ("2.30.0", "2.31.0"):
        release = call(
            "POST",
            "/releases",
            201,
            json=dict(product="OSV runtime", version=version, support_end_date="2099-01-01"),
        )
        ids.append(release["release_id"])
        call(
            "PUT",
            f"/releases/{ids[-1]}/sbom",
            json=dict(
                bomFormat="CycloneDX",
                specVersion="1.6",
                version=1,
                components=[
                    dict(
                        type="library",
                        name="requests",
                        version=version,
                        purl=f"pkg:pypi/requests@{version}?arch=any#source",
                    )
                ],
            ),
        )
    records = [
        rec(
            "CVE-2026-10001",
            affected=[
                dict(
                    package=dict(ecosystem="PyPI", name="requests"),
                    ranges=[
                        dict(
                            type="ECOSYSTEM",
                            events=[dict(introduced="2.3.0"), dict(fixed="2.31.0")],
                        )
                    ],
                )
            ],
        ),
        rec(
            "CVE-2026-10002",
            affected=[dict(package=dict(ecosystem="PyPI", name="requests"), versions=["99.0.0"])],
        ),
    ]
    raw = bundle(records)
    import_raw(raw)
    metadata = inspect()
    assert (
        metadata["content_sha256"] == hashlib.sha256(raw).hexdigest()
        and metadata["record_count"] == 2
    )
    result = call("GET", "/vulnerabilities/CVE-2026-10001/affected-releases")
    assert {r["release_id"] for r in result["supported"]} == {ids[0]}
    assert call("GET", "/vulnerabilities/CVE-2026-10002/affected-releases")["supported"] == []
    assert (
        call("GET", "/vulnerabilities/CVE-2026-99999/affected-releases", 404)["error"]["code"]
        == "CVE_UNKNOWN"
    )
    checks.append(
        "CLI imports raw OSV records with provenance; PyPI range excludes fixed version; known-empty and unknown differ"
    )

    for invalid in (raw, bundle([dict(cve_id="CVE-2026-1", affected_purls=[])])):
        failure = import_raw(invalid, bad_hash=invalid == raw, success=False)
        assert failure.returncode != 0 and inspect()["snapshot_id"] == metadata["snapshot_id"]
    sql(
        "CREATE FUNCTION osv_import_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic OSV failure'; END; $$; CREATE TRIGGER osv_import_reject BEFORE INSERT ON osv_records FOR EACH ROW EXECUTE FUNCTION osv_import_reject();"
    )
    try:
        assert import_raw(raw, success=False).returncode != 0
        assert inspect()["snapshot_id"] == metadata["snapshot_id"]
    finally:
        sql("DROP TRIGGER osv_import_reject ON osv_records; DROP FUNCTION osv_import_reject();")
    checks.append(
        "wrong hash, invalid schema and real SQL failure cannot partially activate a snapshot"
    )

    sql(
        "UPDATE osv_snapshots SET fetched_at=clock_timestamp()-interval '8 days' WHERE snapshot_id=(SELECT snapshot_id FROM osv_active WHERE id=1)"
    )
    assert (
        call("GET", "/vulnerabilities/CVE-2026-99999/affected-releases", 503)["error"]["code"]
        == "VULNERABILITY_SOURCE_UNREACHABLE"
    )
    import_raw(raw)
    unsupported = bundle(
        [
            rec(
                "CVE-2026-10003",
                affected=[
                    dict(
                        package=dict(ecosystem="PyPI", name="requests"),
                        ranges=[
                            dict(
                                type="GIT",
                                repo="https://example.invalid/repo",
                                events=[dict(introduced="0")],
                            )
                        ],
                    )
                ],
            )
        ]
    )
    import_raw(unsupported)
    call("GET", "/vulnerabilities/CVE-2026-10003/affected-releases", 503)
    import_raw(raw)
    checks.append(
        "stale source and unsupported Git comparisons return explicit 503, never empty/unknown"
    )

    call("POST", "/test/reset", 503)
    call("PUT", "/test/vulnerability-source", 503, json=dict(mode="available", records=[]))
    assert call("GET", f"/releases/{ids[0]}")["release_id"] == ids[0]
    assert inspect()["record_count"] == 2
    checks.append(
        "non-grading OSV database refuses resets and fixture injection; domain and snapshot rows survive"
    )

    before = inspect()
    run(prefix + ["restart", "osv"])
    import time

    until = time.monotonic() + 60
    while True:
        try:
            if requests.get(args.base_url + "/health/ready", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            pass
        if time.monotonic() > until:
            raise TimeoutError("OSV API restart failed")
        time.sleep(0.25)
    assert inspect() == before
    assert {
        r["release_id"]
        for r in call("GET", "/vulnerabilities/CVE-2026-10001/affected-releases")["supported"]
    } == {ids[0]}
    checks.append("active snapshot/provenance and exact matching persist across API restart")

    # Simulate lost storage access using only the new, isolated OSV role.
    def limit_connections(value):
        run(
            prefix
            + [
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "cra_test",
                "-d",
                "cra_osv",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                f"ALTER ROLE cra_osv_app CONNECTION LIMIT {value}",
            ]
        )

    limit_connections(0)
    try:
        result = call("GET", "/vulnerabilities/CVE-2026-10001/affected-releases", 503)
        assert result == {
            "error": {
                "code": "VULNERABILITY_SOURCE_UNREACHABLE",
                "message": "Vulnerability storage is unavailable",
            }
        }
    finally:
        limit_connections(-1)
    call("GET", "/vulnerabilities/CVE-2026-10001/affected-releases")
    checks.append(
        "real database connection failure returns sanitized source-unavailable 503 and recovers"
    )

    if args.real_snapshot:
        actual = args.real_snapshot.read_bytes()
        imported = json.loads(import_raw(actual).stdout)
        real_metadata = inspect()
        assert imported["record_count"] == real_metadata["record_count"] == 1
        result = call("GET", "/vulnerabilities/CVE-2023-32681/affected-releases")
        assert {r["release_id"] for r in result["supported"]} == {ids[0]}
        checks.append(
            "real HTTPS-fetched GHSA-j8r2-6x86-q33q snapshot resolves CVE alias and matches 2.30.0 while excluding 2.31.0"
        )
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    output = dict(
        status="passed",
        checks=checks,
        exchanges=observations,
        active_snapshot=inspect(),
        real_snapshot_verified=bool(args.real_snapshot),
    )
    (args.evidence_dir / "osv-runtime.json").write_text(
        json.dumps(output, indent=2), encoding="utf8"
    )
    print(json.dumps(dict(status="passed", checks=checks), indent=2))


if __name__ == "__main__":
    main()
