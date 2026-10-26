"""Tester health must distinguish process life from report-store availability."""

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "tester_health_app", Path(__file__).parents[1] / "app.py"
)
tester = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tester)


def test_tester_liveness_without_database():
    assert tester.live() == {"status": "alive"}


def test_tester_readiness_healthy(monkeypatch):
    calls = []

    class Connection:
        @contextmanager
        def cursor(self):
            yield self

        def execute(self, query):
            calls.append(query)

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(tester.harness.settings, "enabled", True)
    monkeypatch.setattr(tester.harness.settings, "allow_reset", True)
    monkeypatch.setattr(tester.harness.settings, "database_url", "unused")
    monkeypatch.setattr(tester.harness.store, "connection", connection)
    response = tester.ready()
    assert response.status_code == 200 and json.loads(response.body) == {"status": "ready"}
    assert calls == ["SELECT 1"]


@pytest.mark.parametrize("configured", [True, False])
def test_tester_readiness_unavailable_hides_details(monkeypatch, configured):
    def unavailable():
        raise ConnectionError("password=private-value")

    monkeypatch.setattr(tester.harness.settings, "enabled", configured)
    monkeypatch.setattr(tester.harness.settings, "allow_reset", True)
    monkeypatch.setattr(tester.harness.settings, "database_url", "unused")
    monkeypatch.setattr(tester.harness.store, "connection", unavailable)
    response = tester.ready()
    assert response.status_code == 503
    assert json.loads(response.body) == {"status": "unavailable"}
    assert b"private" not in response.body
