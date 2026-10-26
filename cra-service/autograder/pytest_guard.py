"""Harness-only transport policy, loaded explicitly with pytest -p.

The portable suite and its fixtures remain unchanged. All HTTP requests in the
child, including newly created sessions and the concurrent SBOM test, pass this
guard before transport. No redirect is followed, even within the approved origin.
"""

import os
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

import pytest
import requests  # type: ignore[import-untyped]

from .config import HarnessError, normalize_target


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
        return original_send(session, request, **kwargs)

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
