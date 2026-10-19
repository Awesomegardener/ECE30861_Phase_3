"""Deterministic HTTP/SQL race regression, only inside a fresh test Compose API."""

import functools
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import main as application
import uvicorn


def main():
    assert os.environ.get("CRA_RACE_TEST_ALLOW_RESET") == "1", (
        "Explicit isolated reset consent required"
    )
    with application.database() as conn:
        parameters = conn.get_dsn_parameters()
        assert parameters["dbname"] == "cra_test" and parameters["host"] == "db", (
            "Run only inside a fresh isolated test Compose API"
        )

    committed, resume = threading.Event(), threading.Event()
    local = threading.local()
    original_database = application.database
    route = next(
        route
        for route in application.app.routes
        if route.path == "/api/v1/releases" and "POST" in route.methods
    )
    original_create = route.dependant.call

    @contextmanager
    def pause_after_commit(**options):
        with original_database(**options) as conn:
            yield conn
        if getattr(local, "creating", False) and not local.paused:
            local.paused = True
            committed.set()
            assert resume.wait(15), "Reset did not finish during the controlled commit gap"

    @functools.wraps(original_create)
    def controlled_create(*args, **kwargs):
        local.creating, local.paused = True, False
        try:
            return original_create(*args, **kwargs)
        finally:
            local.creating = False

    # Instrument only this separate Python test process. Production code has no test hooks.
    application.database = pause_after_commit
    route.dependant.call = controlled_create
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    server = uvicorn.Server(
        uvicorn.Config(application.app, host="127.0.0.1", log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}/api/v1"
    observations = []

    def request(method, path, body=None):
        req = urllib.request.Request(
            base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "X-User-Id": "isolated-reset-race"},
        )
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    try:
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "Test server failed startup"
            time.sleep(0.02)
        for clock, expected in [
            ("2026-11-01T23:59:59.123456+02:00", "supported"),
            ("2026-11-01T23:30:00-02:00", "unsupported"),
        ]:
            committed.clear()
            resume.clear()
            payload = {
                "product": "IsolatedResetRace",
                "version": uuid.uuid4().hex,
                "support_end_date": "2026-11-01",
            }
            assert request("PUT", "/test/clock", {"now": clock})[0] == 200
            with ThreadPoolExecutor(max_workers=1) as pool:
                creation = pool.submit(request, "POST", "/releases", payload)
                try:
                    assert committed.wait(10), "Creation did not reach its commit boundary"
                    # A real second HTTP request/transaction completes before POST resumes.
                    assert request("POST", "/test/reset")[0] == 204
                    assert request("PUT", "/test/clock", {"now": "2030-01-01T00:00:00Z"})[0] == 200
                    with original_database() as conn, conn.cursor() as cur:
                        cur.execute(
                            "SELECT count(*) AS count FROM releases WHERE product=%s AND version=%s",
                            (payload["product"], payload["version"]),
                        )
                        assert cur.fetchone()["count"] == 0
                finally:
                    resume.set()
                code, body = creation.result(timeout=10)
            observation = {"clock": clock, "creation_status": code, "response": body}
            observations.append(observation)
            print(json.dumps(observation), flush=True)
            assert code == 201, (
                "Reset after successful INSERT commit must not turn creation into 404"
            )
            assert re.fullmatch(r"rel-[0-9a-f]{8}", body["release_id"])
            assert body == {**payload, "release_id": body["release_id"], "support_status": expected}
            # Reset is still destructive; success is not a promise the row survives a later reset.
            assert request("GET", "/releases/" + body["release_id"])[0] == 404
        print(json.dumps({"status": "passed", "cases": len(observations)}), flush=True)
    finally:
        resume.set()
        server.should_exit = True
        if thread.ident is not None:
            thread.join(10)
        listener.close()
        route.dependant.call = original_create
        application.database = original_database
        assert not thread.is_alive(), "Test server did not stop"


if __name__ == "__main__":
    main()
