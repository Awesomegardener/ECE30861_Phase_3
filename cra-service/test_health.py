"""Operational health responses stay small and do not expose connection details."""

import json
from contextlib import contextmanager

import main
import psycopg2
import pytest


def test_liveness_is_independent_of_database(monkeypatch):
    monkeypatch.setattr(
        main, "check_database_ready", lambda: pytest.fail("Liveness must not query DB")
    )
    response = main.health_live()
    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "alive"}
    assert response.headers["Cache-Control"] == "no-store"


def test_readiness_with_healthy_database(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "check_database_ready", lambda: calls.append(True))
    response = main.health_ready()
    assert calls == [True] and response.status_code == 200
    assert json.loads(response.body) == {"status": "ready"}
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "error",
    [
        psycopg2.OperationalError,
        psycopg2.ProgrammingError,
        psycopg2.errors.QueryCanceled,
        RuntimeError,
    ],
)
def test_readiness_with_unavailable_database_hides_details(monkeypatch, error):
    def unavailable():
        raise error("private-host password=do-not-expose-this")

    monkeypatch.setattr(main, "check_database_ready", unavailable)
    response = main.health_ready()
    assert response.status_code == 503
    assert json.loads(response.body) == {"status": "unavailable"}
    assert response.headers["Cache-Control"] == "no-store"
    assert b"private-host" not in response.body and b"password" not in response.body


def test_readiness_uses_read_only_bounded_query(monkeypatch):
    calls, closed = [], []

    class Cursor:
        def execute(self, query):
            calls.append(query)

    class Connection:
        @contextmanager
        def cursor(self):
            yield Cursor()

    @contextmanager
    def database(**options):
        assert options["read_only"] is True
        assert 0 < options["connect_timeout"] <= 2
        assert 0 < options["statement_timeout_ms"] <= 1000
        assert 0 < options["lock_timeout_ms"] <= 1000
        try:
            yield Connection()
        finally:
            closed.append(True)

    monkeypatch.setattr(main, "database", database)
    main.check_database_ready()
    assert calls == ["SELECT 1"] and closed == [True]


def test_health_routes_do_not_expand_shared_api_schema():
    paths = main.app.openapi()["paths"]
    assert "/health/live" not in paths and "/health/ready" not in paths
