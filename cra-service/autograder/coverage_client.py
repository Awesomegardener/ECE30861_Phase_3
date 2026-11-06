"""Authenticated Team 2 extension, used only for explicitly configured origins."""

import requests  # type: ignore[import-untyped]

from .config import HarnessError


class CoverageClient:
    def __init__(self, settings, target, session):
        # Coverage configuration never expands destructive target authorization.
        self.target = settings.authorize(target)
        if self.target not in settings.coverage_targets or len(settings.coverage_token) < 32:
            raise HarnessError(
                503, "COVERAGE_UNAVAILABLE", "Coverage target/key configuration is incomplete"
            )
        self.key = settings.coverage_token
        self.identity = session
        self.timeout = settings.timeout
        self.window = None

    def call(self, operation, body):
        try:
            with requests.Session() as transport:
                transport.trust_env = False
                response = transport.post(
                    self.target + "/internal/coverage/" + operation,
                    json=body,
                    headers={"X-CRA-Coverage-Key": self.key},
                    timeout=30,
                    allow_redirects=False,
                )
            if response.status_code != 200:
                raise ValueError("Coverage control refused")
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Coverage control must return an object")
            return result
        except (requests.RequestException, ValueError):
            # Never echo an upstream body, URL query, key or transport traceback.
            raise HarnessError(
                503, "COVERAGE_UNAVAILABLE", "Target coverage control unavailable or refused"
            ) from None

    def start(self):
        self.window = self.call("start", {**self.identity, "timeout": self.timeout})
        if not all(
            isinstance(self.window.get(k), str) and self.window[k]
            for k in ("run_id", "request_token", "instance_id")
        ):
            raise HarnessError(503, "COVERAGE_UNAVAILABLE", "Invalid coverage start response")
        return self.window

    def finish(self, result):
        assert self.window is not None
        report = {
            **self.identity,
            "checks": [
                {key: check[key] for key in ("id", "title", "passed")} for check in result["checks"]
            ],
        }
        measured = self.call("finish", {"run_id": self.window["run_id"], "report": report})
        for key in ("code", "component", "system"):
            if not isinstance(measured.get(key), dict) or measured[key].get("status") != "measured":
                raise HarnessError(
                    503, "COVERAGE_UNAVAILABLE", "Incomplete target coverage measurement"
                )
        provenance = measured["code"].get("provenance", {})
        if not isinstance(provenance, dict):
            raise HarnessError(503, "COVERAGE_UNAVAILABLE", "Invalid coverage provenance")
        if (
            provenance.get("session_id") != self.identity["session_id"]
            or provenance.get("role") != self.identity["role"]
            or provenance.get("run_id") != self.window["run_id"]
            or provenance.get("instance_id") != self.window["instance_id"]
        ):
            raise HarnessError(503, "COVERAGE_UNAVAILABLE", "Coverage session or instance mismatch")
        self.window = None
        return measured

    def abort(self):
        if self.window:
            try:
                self.call("abort", {"run_id": self.window["run_id"]})
            except HarnessError:
                pass  # Target lease expires; original failure remains authoritative.
            self.window = None
