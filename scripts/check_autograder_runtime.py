"""Restart/timeout/interruption checks ONLY in a dedicated disposable Compose project."""

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


def project_name(value):
    if not re.fullmatch(r"cra-phase3-autograder-[a-z0-9-]+", value):
        raise ValueError("Only a dedicated cra-phase3-autograder-* project is allowed")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=project_name)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--tester-url", default="http://127.0.0.1:18087")
    parser.add_argument("--timeout-port", type=int, default=18088)
    parser.add_argument("--unsafe-port", type=int, default=18093)
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "artifacts/autograder")
    args = parser.parse_args()
    assert re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", args.tester_url)
    observations = []

    def docker(*arguments):
        return subprocess.check_output(
            [args.docker, *arguments], encoding="utf-8", stderr=subprocess.STDOUT, timeout=60
        ).strip()

    def compose(*arguments):
        return docker("compose", "-p", args.project, "-f", str(COMPOSE), *arguments)

    def call(base, method, path, **kwargs):
        response = requests.request(method, base + path, timeout=660, **kwargs)
        response.raise_for_status()
        return response.json()

    def wait(base):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                call(base, "GET", "/health/ready")
                return
            except requests.RequestException:
                time.sleep(0.25)
        raise TimeoutError("Isolated tester readiness timed out")

    # Check provenance before restarting/stopping anything.
    tester = compose("ps", "-q", "tester")
    config = json.loads(docker("inspect", tester))[0]
    assert config["Config"]["Labels"]["com.docker.compose.project"] == args.project
    environment = dict(item.split("=", 1) for item in config["Config"]["Env"] if "=" in item)
    assert environment["AUTOGRADER_DEFAULT_TARGET"] == "http://api:8080"
    assert (
        environment["AUTOGRADER_DATABASE_URL"]
        == "postgresql://cra_harness:local_report_only@db:5432/cra_autograder"
    )
    port = config["NetworkSettings"]["Ports"]["8080/tcp"][0]
    assert port["HostIp"] == "127.0.0.1"
    assert args.tester_url == "http://127.0.0.1:" + port["HostPort"]
    base = args.tester_url

    def sql(database, query):
        return json.loads(
            compose("exec", "-T", "db", "psql", "-U", "cra_test", "-d", database, "-tAc", query)
        )

    roles = sql(
        "cra_test",
        """SELECT json_agg(json_build_object('name', rolname,
        'super', rolsuper, 'createdb', rolcreatedb, 'createrole', rolcreaterole,
        'replication', rolreplication)) FROM pg_roles
        WHERE rolname IN ('cra_grading_app', 'cra_harness')""",
    )
    assert len(roles) == 2 and all(
        not any(v for k, v in role.items() if k != "name") for role in roles
    )
    cross_access = sql(
        "cra_test",
        """SELECT json_build_array(
        has_database_privilege('cra_harness','cra_grading','CONNECT'),
        has_database_privilege('cra_grading_app','cra_autograder','CONNECT'))""",
    )
    assert cross_access == [False, False]
    assert sql(
        "cra_grading",
        """SELECT json_build_array(
        has_schema_privilege('cra_grading_app','public','USAGE'),
        has_schema_privilege('cra_grading_app','public','CREATE'))""",
    ) == [True, True]
    observations.append(
        {
            "check": "separate databases and ordinary roles have intended schema access and no cross-database CONNECT",
            "passed": True,
        }
    )

    # Reuse actual saved complete result from the HTTP integration tests.
    report = json.loads((args.evidence_dir / "tester-report.json").read_text())
    assert report["result"] == "pass" and report["summary"]["passed"] == 157
    route = "/test/report?session_id=" + report["session_id"]
    before = call(base, "GET", route)
    api_id = compose("ps", "-q", "api")
    api_config = json.loads(docker("inspect", api_id))[0]
    api_environment = dict(
        value.split("=", 1) for value in api_config["Config"]["Env"] if "=" in value
    )
    assert (
        api_environment["DATABASE_URL"]
        == "postgresql://cra_grading_app:local_grading_only@db:5432/cra_grading"
    )
    assert api_environment["AUTOGRADER_RESET_DATABASE"] == "cra_grading"
    api_port = api_config["NetworkSettings"]["Ports"]["8080/tcp"][0]
    assert api_port["HostIp"] == "127.0.0.1"
    api_base = "http://127.0.0.1:" + api_port["HostPort"]
    call(api_base, "POST", "/test/setup")
    assert call(base, "GET", route) == before
    observations.append(
        {
            "check": "domain reset cannot erase the separate database's completed report",
            "passed": True,
        }
    )
    compose("restart", "tester")
    wait(base)
    assert call(base, "GET", route) == before
    observations.append({"check": "complete report survives tester restart", "passed": True})

    # Kill a real active acceptance run; the durable record must recover as error.
    identifier = call(base, "POST", "/test/setup")["session_id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(call, base, "POST", "/test/run", json={"session_id": identifier})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = call(base, "GET", "/test/report?session_id=" + identifier)
            if current["running"]:
                break
            time.sleep(0.05)
        assert current["running"]
        compose("kill", "tester")
        try:
            running.result(timeout=15)
        except requests.RequestException:
            pass
        else:
            raise AssertionError("Killed run unexpectedly returned success")
    compose("start", "tester")
    wait(base)
    recovered = call(base, "GET", "/test/report?session_id=" + identifier)
    assert recovered["status"] == "completed" and recovered["result"] == "error"
    assert recovered["error"] and not recovered["running"]
    assert call(base, "GET", route) == before
    observations.append(
        {"check": "hard interruption recovered, old completed report intact", "passed": True}
    )

    # A separate instance still shares the same metadata lock and reports.
    name = args.project + "-timeout-" + uuid.uuid4().hex[:8]
    try:
        compose(
            "run",
            "--no-deps",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{args.timeout_port}:9090",
            "-e",
            "PORT=9090",
            "-e",
            "AUTOGRADER_RUN_TIMEOUT_SECONDS=1",
            "tester",
        )
        timeout_base = f"http://127.0.0.1:{args.timeout_port}"
        wait(timeout_base)
        assert call(timeout_base, "GET", route) == before
        identifier = call(timeout_base, "POST", "/test/setup")["session_id"]
        outcome = call(timeout_base, "POST", "/test/run", json={"session_id": identifier})
        assert outcome["result"] == "error" and outcome["summary"]["passed"] == 0
        result = call(base, "GET", "/test/report?session_id=" + identifier)
        assert result["error"].startswith("TimeoutError")
        # Inspect cmdlines via a separate Python process; exclude this check itself.
        child_check = "from pathlib import Path; import os; print(sum(b'pytest' in p.read_bytes() for p in Path('/proc').glob('[0-9]*/cmdline') if p.parent.name != str(os.getpid())))"
        assert docker("exec", name, "python", "-c", child_check) == "0"
        observations.append(
            {
                "check": "real subprocess timeout terminates child and persists error across instances",
                "passed": True,
            }
        )
    finally:
        # Stop only the checked newly created container. No removal/volume deletion.
        docker("stop", name)

    # A wrong approval name cannot unlock reset, even with the right grading DSN.
    name = args.project + "-unsafe-" + uuid.uuid4().hex[:8]
    try:
        release = call(
            api_base,
            "POST",
            "/api/v1/releases",
            json={
                "product": "Must survive rejected adapter setup",
                "version": uuid.uuid4().hex,
                "support_end_date": "2099-01-01",
            },
            headers={"X-User-Id": "isolated-safety-test"},
        )
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
        unsafe_base = f"http://127.0.0.1:{args.unsafe_port}"
        wait(unsafe_base)
        assert call(unsafe_base, "GET", "/test")["reset_ready"] is False
        response = requests.post(unsafe_base + "/test/setup", timeout=10)
        assert response.status_code == 503 and response.json()["error"]["code"] == "RESET_DISABLED"
        assert call(api_base, "GET", "/api/v1/releases/" + release["release_id"]) == release
        observations.append(
            {
                "check": "real HTTP setup with retained database approval is refused without deleting the new grading release",
                "passed": True,
            }
        )
    finally:
        docker("stop", name)

    destination = args.evidence_dir / "runtime-results.json"
    destination.write_text(json.dumps(observations, indent=2), encoding="utf-8")
    print(json.dumps(observations, indent=2))


if __name__ == "__main__":
    main()
