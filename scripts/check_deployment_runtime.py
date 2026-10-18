"""Exercise real container ports/health/restarts only in an isolated test project."""

import argparse
import datetime
import http.client
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "cra-service/docker-compose.test.yml"
TEST_DSN = "postgresql://cra_test:local_test_only@db:5432/cra_test"


def validate_project(value):
    if not re.fullmatch(r"cra-phase3-deployment-[a-z0-9][a-z0-9-]*", value):
        raise ValueError(
            "Use a fresh cra-phase3-deployment-* project; original/test stacks are refused"
        )
    return value


def wait_for_ready(check, *, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            check()
            return
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            ConnectionError,
            TimeoutError,
            AssertionError,
        ):
            time.sleep(0.25)
    raise TimeoutError("Isolated API did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=validate_project)
    parser.add_argument("--docker", default="docker")
    parser.add_argument(
        "--evidence-dir", type=Path, default=ROOT / "artifacts/deployment-readiness"
    )
    args = parser.parse_args()
    observations, created = [], []
    status = "failed"

    def docker(*command, timeout=60):
        return subprocess.check_output(
            [args.docker, *command],
            text=True,
            encoding="utf-8",
            stderr=subprocess.STDOUT,
            timeout=timeout,
        ).strip()

    def compose(*command):
        return docker("compose", "-p", args.project, "-f", str(COMPOSE), *command)

    def inspect(identifier):
        return json.loads(docker("inspect", identifier))[0]

    def request(base, path, expected=200, method="GET", payload=None):
        start = time.monotonic()
        headers = {"Content-Type": "application/json"}
        if method != "GET":
            headers["X-User-Id"] = "deployment-runtime-check"
        req = urllib.request.Request(
            base + path,
            method=method,
            headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = json.load(response)
            observations.append(
                {
                    "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "url": base + path,
                    "method": method,
                    "status": response.status,
                    "seconds": round(time.monotonic() - start, 3),
                    "body": body,
                }
            )
            assert response.status == expected, (path, response.status, body)
            if path.startswith("/health/"):
                assert response.headers["Cache-Control"] == "no-store"
            return body

    def ready(base):
        def check():
            assert request(base, "/health/ready") == {"status": "ready"}

        wait_for_ready(check)

    def base_url(data, port):
        bindings = data["NetworkSettings"]["Ports"][f"{port}/tcp"]
        assert len(bindings) == 1 and bindings[0]["HostIp"] == "127.0.0.1"
        return "http://127.0.0.1:" + bindings[0]["HostPort"]

    api, db = compose("ps", "-q", "api"), compose("ps", "-q", "db")
    assert api and db, "Start a fresh isolated test project first"
    api_data, db_data = inspect(api), inspect(db)
    for data, service in ((api_data, "api"), (db_data, "db")):
        assert data["Config"]["Labels"]["com.docker.compose.project"] == args.project
        assert data["Config"]["Labels"]["com.docker.compose.service"] == service
    api_env = dict(value.split("=", 1) for value in api_data["Config"]["Env"] if "=" in value)
    db_env = dict(value.split("=", 1) for value in db_data["Config"]["Env"] if "=" in value)
    assert api_env.get("DATABASE_URL") == TEST_DSN, "Refuse non-test API connection"
    assert db_env.get("POSTGRES_DB") == db_env.get("POSTGRES_USER") == "cra_test"
    default = base_url(api_data, 8080)
    image = api_data["Image"]
    networks = list(api_data["NetworkSettings"]["Networks"])
    assert len(networks) == 1
    ready(default)
    assert request(default, "/health/live") == {"status": "alive"}
    schema = request(default, "/openapi.json")
    assert "/health/live" not in schema["paths"] and "/health/ready" not in schema["paths"]

    # These records belong only to the new test project. No reset is called here.
    release = request(
        default,
        "/api/v1/releases",
        expected=201,
        method="POST",
        payload={
            "product": "DeploymentPersistence",
            "version": uuid.uuid4().hex,
            "support_end_date": "2099-01-01",
        },
    )
    path = "/api/v1/releases/" + release["release_id"]
    request(
        default,
        path + "/sbom",
        method="PUT",
        payload={
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "application",
                    "name": "parent",
                    "version": "1",
                    "components": [{"type": "library", "name": "child", "version": "2"}],
                }
            ],
        },
    )

    def persisted():
        inventory = request(default, path + "/components")
        inventory["components"].sort(key=lambda c: (c["name"], c["version"], c.get("purl") or ""))
        return {"release": request(default, path), "inventory": inventory}

    before = persisted()
    database_stopped = False
    try:
        custom = docker(
            "run",
            "-d",
            "--name",
            args.project + "-port-" + uuid.uuid4().hex[:8],
            "--network",
            networks[0],
            "-e",
            "DATABASE_URL=" + TEST_DSN,
            "-e",
            "PORT=9090",
            "-p",
            "127.0.0.1::9090",
            image,
        )
        created.append(custom)
        custom_url = base_url(inspect(custom), 9090)
        ready(custom_url)
        assert request(custom_url, "/health/live") == {"status": "alive"}

        invalid = docker(
            "run",
            "-d",
            "--name",
            args.project + "-invalid-port-" + uuid.uuid4().hex[:8],
            "-e",
            "PORT=not-a-port",
            image,
        )
        created.append(invalid)
        assert int(docker("wait", invalid, timeout=15)) != 0

        database_stopped = True
        compose("stop", "db")
        assert request(default, "/health/ready", expected=503) == {"status": "unavailable"}
        assert request(default, "/health/live") == {"status": "alive"}
        waiting = docker(
            "run",
            "-d",
            "--name",
            args.project + "-db-retry-" + uuid.uuid4().hex[:8],
            "--network",
            networks[0],
            "-e",
            "DATABASE_URL=" + TEST_DSN,
            "-e",
            "PORT=9091",
            "-p",
            "127.0.0.1::9091",
            image,
        )
        created.append(waiting)

        def startup_retried():
            assert '"event": "database_not_ready"' in docker("logs", waiting)

        wait_for_ready(startup_retried, timeout=15)
        compose("start", "db")
        ready(default)
        database_stopped = False
        ready(custom_url)
        ready(base_url(inspect(waiting), 9091))
        assert persisted() == before
        compose("restart", "api")
        ready(default)
        assert persisted() == before
        docker("stop", "--time", "10", custom)
        assert inspect(custom)["State"]["ExitCode"] == 0, "SIGTERM should reach Uvicorn cleanly"
        status = "passed"
        print(
            "PASS: default 8080, PORT=9090, invalid PORT, live/ready outage/recovery, "
            "cold-start DB retry, API/DB restart persistence and graceful shutdown"
        )
    finally:
        if database_stopped:
            compose("start", "db")
        for container in created:
            if inspect(container)["State"]["Running"]:
                docker("stop", "--time", "10", container)
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
        (args.evidence_dir / "deployment-runtime.json").write_text(
            json.dumps(
                {
                    "status": status,
                    "completed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "project": args.project,
                    "image": image,
                    "exchanges": observations,
                    "new_containers_retained": created,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
