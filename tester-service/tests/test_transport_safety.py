"""No network: fake transport proves redirects and alternate targets never send."""

import io
from types import SimpleNamespace

import pytest
import requests
from autograder.config import TEAM2, TEAM6, HarnessError, Settings
from autograder.pytest_guard import guard_requests, pytest_configure
from requests.adapters import BaseAdapter

APPROVED = "https://approved.invalid"
UNAPPROVED = "https://unapproved.invalid"


class RecordingAdapter(BaseAdapter):
    def __init__(self, status=204, location=None):
        self.calls = []
        self.status, self.location = status, location

    def send(self, request, **kwargs):
        self.calls.append((request.method, request.url, kwargs))
        response = requests.Response()
        response.status_code = self.status
        response.request = request
        response.url = request.url
        response.raw = io.BytesIO(b"")
        response._content = b""
        if self.location:
            response.headers["Location"] = self.location
        return response

    def close(self):
        pass


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("destination", [UNAPPROVED, APPROVED])
def test_redirect_never_forwards_destructive_request(status, method, destination):
    adapter = RecordingAdapter(status, destination + "/api/v1/test/reset")
    with requests.Session() as session, guard_requests(APPROVED):
        session.mount("https://", adapter)
        response = session.request(method, APPROVED + "/api/v1/test/reset", allow_redirects=True)
    assert response.status_code == status
    assert [(method, url) for method, url, _ in adapter.calls] == [
        (method, APPROVED + "/api/v1/test/reset")
    ]


@pytest.mark.parametrize(
    "url",
    [
        UNAPPROVED + "/api/v1/test/reset",
        APPROVED + "/test/setup",
        "https://user:pass@approved.invalid/api/v1/test/reset",
    ],
)
def test_every_session_rejects_unapproved_prepared_request_before_transport(url):
    adapter = RecordingAdapter()
    with requests.Session() as session, guard_requests(APPROVED):
        session.mount("https://", adapter)
        with pytest.raises(requests.exceptions.InvalidURL):
            session.post(url)
    assert adapter.calls == []


def test_requests_to_selected_target_work_and_ignore_environment_proxies(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://unapproved.invalid:8888")
    adapter = RecordingAdapter()
    with requests.Session() as session, guard_requests(APPROVED):
        session.mount("https://", adapter)
        assert session.get(APPROVED + "/api/v1/releases/example").status_code == 204
    assert len(adapter.calls) == 1 and adapter.calls[0][2]["proxies"] == {}


def test_guard_is_harness_only_and_restores_original_transport():
    original = requests.Session.send
    with guard_requests(APPROVED):
        assert requests.Session.send is not original
    assert requests.Session.send is original


def test_plugin_refuses_missing_target(monkeypatch):
    monkeypatch.delenv("CRA_HARNESS_TARGET", raising=False)
    with pytest.raises(pytest.UsageError):
        pytest_configure(SimpleNamespace())


@pytest.fixture
def enabled_environment(monkeypatch):
    for key in ("AUTOGRADER_DEFAULT_TARGET", "AUTOGRADER_APPROVED_TARGETS", "PORT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AUTOGRADER_ENABLED", "true")
    monkeypatch.setenv("AUTOGRADER_ALLOW_RESET", "true")
    monkeypatch.setenv("AUTOGRADER_DATABASE_URL", "unused-test-dsn")


@pytest.mark.parametrize("port", ["8080", "9090"])
def test_system_defaults_only_to_its_own_port(enabled_environment, monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    settings = Settings.environment("system")
    assert settings.authorize() == f"http://127.0.0.1:{port}"
    assert settings.approved_targets == {f"http://127.0.0.1:{port}"}
    for remote in (TEAM2, TEAM6):
        with pytest.raises(HarnessError):
            settings.authorize(remote)


@pytest.mark.parametrize("remote", [TEAM2, TEAM6, "http://127.0.0.1:9999"])
def test_system_refuses_remote_or_wrong_port_even_if_configured_and_allowlisted(
    enabled_environment, monkeypatch, remote
):
    monkeypatch.setenv("AUTOGRADER_DEFAULT_TARGET", remote)
    monkeypatch.setenv("AUTOGRADER_APPROVED_TARGETS", remote)
    with pytest.raises(HarnessError) as error:
        Settings.environment("system").authorize()
    assert error.value.status == 500
