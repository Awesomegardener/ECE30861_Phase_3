"""Validated, bounded target RPCs. Never follow redirects or inherit proxies."""

import time

import requests  # type: ignore[import-untyped]

from .config import HarnessError

SOURCES = {"tester", "system", "communication", "unknown"}


class TargetClient:
    def __init__(self, settings, target):
        self.target = settings.authorize(target)
        self.settings = settings

    def request(self, method, path, *, timeout, **kwargs):
        try:
            with requests.Session() as client:
                client.trust_env = False
                return client.request(
                    method,
                    self.target + path,
                    timeout=max(0.05, timeout),
                    allow_redirects=False,
                    **kwargs,
                )
        except requests.RequestException:
            raise HarnessError(
                500, "COMMUNICATION_FAILURE", "No target response was available", "communication"
            ) from None

    def setup(self, identifier, starting):
        response = self.request(
            "POST",
            "/test/setup",
            timeout=self.settings.setup_timeout,
            json={"session_id": identifier, "setup": starting},
        )
        try:
            body = response.json()
        except ValueError:
            raise HarnessError(
                500, "INVALID_SYSTEM_RESPONSE", "System setup returned invalid JSON", "system"
            ) from None
        if response.status_code != 201:
            if (
                isinstance(body, dict)
                and isinstance(body.get("message"), str)
                and body["message"].strip()
                and isinstance(body.get("source"), str)
                and body.get("source") in SOURCES
            ):
                raise HarnessError(
                    response.status_code, "SYSTEM_SETUP_FAILED", body["message"], body["source"]
                )
            raise HarnessError(
                500,
                "INVALID_SYSTEM_RESPONSE",
                "System setup returned an invalid error envelope",
                "system",
            )
        if not isinstance(body, dict) or body.get("session_id") != identifier:
            raise HarnessError(
                500,
                "SESSION_MISMATCH",
                "System setup did not return the supplied session_id",
                "system",
            )

    def code_coverage(self, identifier, deadline):
        from .coverage import unavailable_coverage

        if time.monotonic() >= deadline:
            return unavailable_coverage("Run budget exhausted before system coverage retrieval")[
                "code"
            ]
        try:
            response = self.request(
                "GET",
                "/test/report",
                timeout=min(30, deadline - time.monotonic()),
                params={"session_id": identifier},
            )
            data = response.json()
            if response.status_code != 200 or data.get("session_id") != identifier:
                raise ValueError()
            code = data["coverage"]["code"]
            covered, total, basis = (code[k] for k in ("covered", "total", "basis"))
            if not isinstance(basis, str) or not basis.strip():
                raise ValueError()
            if (covered, total) != (None, None) and not (
                type(covered) is int and type(total) is int and 0 <= covered <= total
            ):
                raise ValueError()
            return code
        except (HarnessError, ValueError, KeyError, TypeError, AttributeError):
            return unavailable_coverage(
                "System /test/report measurement unavailable or invalid; no counts inferred"
            )["code"]
