"""Persistence and reset-safety checks in a dedicated disposable Compose project.

Abort/report behavior is exercised by test_http.py. A hard service crash is
allowed to leave no retrievable report by the course interface; lookup must not
invent or mutate a completed report to recover one.
"""

import argparse
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def project_name(value):
    if not re.fullmatch(r"cra-phase3-autograder-[a-z0-9-]+", value):
        raise ValueError("Only a dedicated cra-phase3-autograder-* project is allowed")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=project_name)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--tester-url", default="http://127.0.0.1:18087")
    parser.add_argument("--unsafe-port", type=int, default=18093)
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "artifacts/autograder")
    args = parser.parse_args()
    assert re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", args.tester_url)

    def docker(*arguments):
        return subprocess.check_output(
            [args.docker, *arguments], encoding="utf-8", stderr=subprocess.STDOUT, timeout=60
        ).strip()

    def compose(*arguments):
        return docker(
            "compose",
            "-p",
            args.project,
            "-f",
            str(ROOT / "tester-service/docker-compose.test.yml"),
            *arguments,
        )

    def inspect(service):
        config = json.loads(docker("inspect", compose("ps", "-q", service)))[0]
        assert config["Config"]["Labels"]["com.docker.compose.project"] == args.project
        return config

    def origin(config):
        port = config["NetworkSettings"]["Ports"]["8080/tcp"][0]
        assert port["HostIp"] == "127.0.0.1"
        return "http://127.0.0.1:" + port["HostPort"]

    def call(base, method, path, expected=200, **kwargs):
        response = requests.request(method, base + path, timeout=660, **kwargs)
        assert response.status_code == expected, response.text[:1000]
        return response.json()

    def wait(base):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                call(base, "GET", "/health/ready")
                return
            except (requests.RequestException, AssertionError):
                time.sleep(0.25)
        raise TimeoutError("Isolated service readiness timed out")

    tester, api = inspect("tester"), inspect("api")
    assert origin(tester) == args.tester_url
    api_base = origin(api)
    env = dict(item.split("=", 1) for item in api["Config"]["Env"] if "=" in item)
    assert (
        env["DATABASE_URL"] == "postgresql://cra_grading_app:local_grading_only@db:5432/cra_grading"
    )
    assert env["AUTOGRADER_RESET_DATABASE"] == "cra_grading"

    def sql(database, query):
        return json.loads(
            compose("exec", "-T", "db", "psql", "-U", "cra_test", "-d", database, "-tAc", query)
        )

    assert sql(
        "cra_test",
        """SELECT json_build_array(
        has_database_privilege('cra_harness','cra_grading','CONNECT'),
        has_database_privilege('cra_grading_app','cra_autograder','CONNECT'))""",
    ) == [False, False]
    roles = sql(
        "cra_test",
        """SELECT json_agg(json_build_object('name',rolname,'super',rolsuper,
        'createdb',rolcreatedb,'createrole',rolcreaterole,'replication',rolreplication))
        FROM pg_roles WHERE rolname IN ('cra_grading_app','cra_harness')""",
    )
    assert len(roles) == 2 and all(
        not any(v for k, v in row.items() if k != "name") for row in roles
    )
    observations = [{"check": "isolated databases and ordinary roles", "passed": True}]

    report = json.loads((args.evidence_dir / "tester-report.json").read_text())
    assert len(report["results"]) == 353 and all(
        item["outcome"] == "pass" for item in report["results"]
    )
    query = {"session_id": report["session_id"]}
    before = call(args.tester_url, "GET", "/test/report", params=query)
    assert before == report
    call(
        api_base,
        "POST",
        "/test/setup",
        201,
        json={"session_id": "reset-" + uuid.uuid4().hex, "setup": {}},
    )
    assert call(args.tester_url, "GET", "/test/report", params=query) == before
    compose("restart", "tester")
    wait(args.tester_url)
    assert call(args.tester_url, "GET", "/test/report", params=query) == before
    call(args.tester_url, "POST", "/test/run", 409, json=query)
    observations.append(
        {
            "check": "immutable terminal report and consumed run survive reset and tester restart",
            "passed": True,
        }
    )

    # Deliberately wrong reset approval must not erase any grading data.
    release = call(
        api_base,
        "POST",
        "/api/v1/releases",
        201,
        json={"product": "Preserve", "version": uuid.uuid4().hex, "support_end_date": "2099-01-01"},
        headers={"X-User-Id": "isolated-safety-test"},
    )
    name = args.project + "-unsafe-" + uuid.uuid4().hex[:8]
    try:
        compose(
            "run",
            "--no-deps",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{args.unsafe_port}:8080",
            "-e",
            "AUTOGRADER_RESET_DATABASE=cra_db",
            "api",
        )
        unsafe = f"http://127.0.0.1:{args.unsafe_port}"
        wait(unsafe)
        error = call(
            unsafe, "POST", "/test/setup", 500, json={"session_id": uuid.uuid4().hex, "setup": {}}
        )
        assert error["source"] == "system" and error["message"]
        assert call(api_base, "GET", "/api/v1/releases/" + release["release_id"]) == release
        observations.append(
            {
                "check": "incorrect reset approval refuses setup without deleting domain data",
                "passed": True,
            }
        )
    finally:
        docker("stop", name)
    (args.evidence_dir / "runtime-results.json").write_text(json.dumps(observations, indent=2))
    print(json.dumps(observations, indent=2))


if __name__ == "__main__":
    main()
