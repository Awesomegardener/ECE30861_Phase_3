"""Persistence and rollback evidence ONLY in the fresh local harness project."""

import argparse
import json
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "tester-service/docker-compose.test.yml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--base-url", default="http://127.0.0.1:18086")
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "artifacts/phase4")
    args = parser.parse_args()
    if not re.fullmatch(r"cra-phase3-autograder-[a-z0-9-]+", args.project):
        raise ValueError("Requires a new isolated cra-phase3-autograder-* project")
    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", args.base_url):
        raise ValueError("Only a verified local loopback target is permitted")

    def docker(*command):
        return subprocess.check_output(
            [args.docker, *command], encoding="utf8", timeout=60, stderr=subprocess.STDOUT
        ).strip()

    def compose(*command):
        return docker("compose", "-p", args.project, "-f", str(COMPOSE), *command)

    identifier = compose("ps", "-q", "api")
    config = json.loads(docker("inspect", identifier))[0]
    assert config["Config"]["Labels"]["com.docker.compose.project"] == args.project
    environment = dict(s.split("=", 1) for s in config["Config"]["Env"] if "=" in s)
    assert (
        environment["DATABASE_URL"]
        == "postgresql://cra_grading_app:local_grading_only@db:5432/cra_grading"
    )
    port = config["NetworkSettings"]["Ports"]["8080/tcp"][0]
    assert port["HostIp"] == "127.0.0.1"
    assert args.base_url == "http://127.0.0.1:" + port["HostPort"]

    def call(method, path, status=200, **kwargs):
        response = requests.request(
            method,
            args.base_url + "/api/v1" + path,
            timeout=10,
            headers={"X-User-Id": "phase4-runtime"},
            **kwargs,
        )
        assert response.status_code == status, response.text
        return response.json()

    def sql(statement):
        return compose(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "cra_test",
            "-d",
            "cra_grading",
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            statement,
        )

    observations = []
    incident = call(
        "POST",
        "/incidents",
        201,
        json=dict(
            awareness_at="2026-11-01T00:00:00Z",
            classification="mandatory",
            rationale="Persistence oracle",
            cve_id="CVE-2026-55",
        ),
    )
    path = "/incidents/" + incident["incident_id"]
    call("PATCH", path, json={"fix_available_at": "2026-11-03T00:00:00Z"})
    call(
        "POST",
        path + "/submissions",
        201,
        json=dict(stage="early_warning", submitted_at="2026-11-02T00:00:00Z"),
    )
    call(
        "PUT",
        "/test/vulnerability-source",
        json=dict(mode="available", records=[dict(cve_id="CVE-2026-55", affected_purls=[])]),
    )
    before = call("GET", path)
    source_before = call("GET", "/vulnerabilities/CVE-2026-55/affected-releases")
    compose("restart", "api")
    end = time.monotonic() + 60
    while True:
        try:
            ready = requests.get(args.base_url + "/health/ready", timeout=3)
            if ready.status_code == 200:
                break
        except requests.RequestException:
            pass
        if time.monotonic() >= end:
            raise TimeoutError("Restart readiness failed")
        time.sleep(0.25)
    assert call("GET", path) == before
    assert call("GET", "/vulnerabilities/CVE-2026-55/affected-releases") == source_before
    observations.append(
        "incident, submission, clock-derived deadlines and source survive API restart exactly"
    )

    # A real PostgreSQL error must roll back and return a sanitized envelope.
    # DDL is scoped to this verified disposable project, never an existing volume.
    sql("""CREATE FUNCTION phase4_test_reject() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'synthetic failure, password=must-not-escape'; END; $$;
        CREATE TRIGGER phase4_test_reject BEFORE INSERT ON incident_submissions
        FOR EACH ROW EXECUTE FUNCTION phase4_test_reject();""")
    try:
        error = call(
            "POST",
            path + "/submissions",
            500,
            json=dict(stage="final_report", submitted_at="2026-11-10T00:00:00Z"),
        )
        assert error == {
            "error": {"code": "DATABASE_ERROR", "message": "Database operation failed"}
        }
        assert call("GET", path) == before
    finally:
        sql(
            "DROP TRIGGER phase4_test_reject ON incident_submissions; DROP FUNCTION phase4_test_reject();"
        )
    observations.append(
        "submission SQL failure rolls back, closes resources and exposes no exception details"
    )

    # Independently concurrent updates serialize on the incident row; no lost stages.
    def submit(stage):
        return call(
            "POST",
            path + "/submissions",
            409 if stage == "early_warning" else 201,
            json=dict(stage=stage, submitted_at="2026-11-02T00:00:00Z"),
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(submit, ["early_warning", "vulnerability_notification", "final_report"]))
    assert all(v["submitted_at"] is not None for v in call("GET", path)["deadlines"].values())
    # Count only this run's incident; prior evidence rows may remain on a rerun.
    count_program = """import sys, main
with main.database() as conn, conn.cursor() as cur:
 cur.execute('SELECT count(*) AS n FROM incident_submissions WHERE incident_id=%s AND recorded_by=%s', (sys.argv[1], 'phase4-runtime'))
 print(cur.fetchone()['n'])
"""
    assert (
        compose("exec", "-T", "api", "python", "-c", count_program, incident["incident_id"]) == "3"
    )
    observations.append(
        "concurrent duplicate returns 409; exactly three attributed stage records remain"
    )

    # Exercise the fail-closed source configuration inside this same new DB.
    program = """import os, main, phase4
from fastapi import HTTPException
for expected in ('cra_phase3', 'cra_test'):
 os.environ['VULNERABILITY_TEST_MODE']='true'
 os.environ['VULNERABILITY_TEST_DATABASE']=expected
 with main.database() as conn, conn.cursor() as cur:
  try: phase4.require_test_source(cur)
  except HTTPException as error: assert error.status_code==503
  else: raise AssertionError('Unsafe source configuration accepted')
print('guarded')
"""
    assert compose("exec", "-T", "api", "python", "-c", program) == "guarded"
    observations.append(
        "real database rejects retained-name and mismatched test-source approval without mutation"
    )

    # The original API permits long schema-valid PURLs. Indexing must not add a
    # B-tree entry-size limit to those inputs. Use varied text, not compressible padding.
    import hashlib

    long_purl = (
        "pkg:generic/"
        + "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(90))
        + "@1"
    )
    release = call(
        "POST",
        "/releases",
        201,
        json=dict(product="Long PURL", version=uuid.uuid4().hex, support_end_date="2099-01-01"),
    )
    call(
        "PUT",
        "/releases/" + release["release_id"] + "/sbom",
        json=dict(
            bomFormat="CycloneDX",
            specVersion="1.6",
            version=1,
            components=[dict(type="library", name="long-component", version="1", purl=long_purl)],
        ),
    )
    call(
        "PUT",
        "/test/vulnerability-source",
        json=dict(
            mode="available", records=[dict(cve_id="CVE-2026-77", affected_purls=[long_purl])]
        ),
    )
    match = call("GET", "/vulnerabilities/CVE-2026-77/affected-releases")
    assert match["supported"][0]["matched_components"][0]["purl"] == long_purl
    assert "USING hash" in sql(
        "SELECT indexdef FROM pg_indexes WHERE indexname='components_purl_lookup'"
    )
    observations.append(
        "valid long PURL ingestion and exact CVE matching preserved with a hash equality index"
    )

    # Unique product proves creating after a prior failure still works.
    call(
        "POST",
        "/releases",
        201,
        json=dict(
            product="Phase4 runtime", version=uuid.uuid4().hex, support_end_date="2099-01-01"
        ),
    )
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    result = dict(
        status="passed",
        checks=observations,
        target=args.base_url,
        incident_before_restart=before,
        project=args.project,
    )
    (args.evidence_dir / "phase4-runtime.json").write_text(
        json.dumps(result, indent=2), encoding="utf8"
    )
    print(json.dumps(dict(status="passed", checks=observations), indent=2))


if __name__ == "__main__":
    main()
