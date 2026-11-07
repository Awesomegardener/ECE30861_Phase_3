"""Harness-only transport policy, loaded explicitly with pytest -p.

The portable suite and its fixtures remain unchanged. All HTTP requests in the
child, including newly created sessions and the concurrent SBOM test, pass this
guard before transport. No redirect is followed, even within the approved origin.
"""

import json
import os
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

import pytest
import requests  # type: ignore[import-untyped]

from .config import HarnessError, normalize_target

TEST_ID = ""
LAST_RESPONSE: dict[str, dict[str, str | None]] = {}


def journal(event):
    path = os.getenv("CRA_HARNESS_JOURNAL")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(json.dumps(event) + "\n")


def pytest_runtest_logstart(nodeid, location):
    file, _, name = nodeid.partition("::")
    journal(
        {
            "event": "start",
            "test_id": "cra-service/" + file.replace("\\", "/").rsplit("/", 1)[-1] + "::" + name,
        }
    )


def pytest_runtest_logreport(report):
    if report.when == "setup" and report.passed or report.when == "teardown" and report.passed:
        return
    file, _, name = report.nodeid.partition("::")
    identifier = "cra-service/" + file.replace("\\", "/").rsplit("/", 1)[-1] + "::" + name
    outcome = "pass" if report.passed else "skip" if report.skipped else "fail"
    message = (
        "All assertions matched expected behavior."
        if report.passed
        else str(report.longrepr)[-8000:]
    )
    from http_evidence import redact_text

    event = {
        "event": "result",
        "test_id": identifier,
        "outcome": outcome,
        "message": redact_text(message) or "No test detail available",
    }
    if report.failed:
        problem = LAST_RESPONSE.get(identifier, {})
        source = problem.get("source")
        crash = str(getattr(getattr(report.longrepr, "reprcrash", None), "message", ""))
        assertion = "AssertionError" in crash or crash.startswith("assert ")
        if source in {"system", "communication"} or report.when != "call" or not assertion:
            event.update(
                outcome="error", source=source or ("tester" if not assertion else "unknown")
            )
    journal(event)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global TEST_ID
    file, _, name = item.nodeid.partition("::")
    TEST_ID = "cra-service/" + file.replace("\\", "/").rsplit("/", 1)[-1] + "::" + name
    try:
        yield
    finally:
        TEST_ID = ""


@contextmanager
def guard_requests(target):
    approved = normalize_target(target)
    original_send = requests.Session.send

    def send(session, request, **kwargs):
        parts = urlsplit(request.url)
        try:
            origin = normalize_target(urlunsplit((parts.scheme, parts.netloc, "", "", "")))
        except (HarnessError, ValueError):
            raise requests.exceptions.InvalidURL(
                "Harness rejected an invalid request destination"
            ) from None
        if origin != approved or not parts.path.startswith("/api/v1/"):
            raise requests.exceptions.InvalidURL(
                "Harness blocked a request outside the selected CRA target"
            )
        kwargs["allow_redirects"] = False
        kwargs["proxies"] = {}  # Do not route through inherited proxy settings.
        if os.getenv("CRA_HARNESS_SESSION_ID"):
            request.headers["X-Test-Session-Id"] = os.environ["CRA_HARNESS_SESSION_ID"]
        try:
            response = original_send(session, request, **kwargs)
        except requests.RequestException:
            LAST_RESPONSE[TEST_ID] = {"source": "communication"}
            raise
        LAST_RESPONSE[TEST_ID] = {
            "source": "system"
            if response.status_code >= 500 or response.headers.get("X-Test-Session-Conflict") == "1"
            else None
        }
        return response

    with patch.object(requests.Session, "send", send):
        yield


def pytest_configure(config):
    target = os.getenv("CRA_HARNESS_TARGET")
    if not target:
        raise pytest.UsageError("Harness transport guard requires CRA_HARNESS_TARGET")
    context = guard_requests(target)
    context.__enter__()
    config._cra_transport_guard = context


def pytest_unconfigure(config):
    context = getattr(config, "_cra_transport_guard", None)
    if context is not None:
        context.__exit__(None, None, None)
