"""Startup must tolerate transient DB failures and stop after its retry budget."""

import asyncio

import main
import psycopg2
import pytest


@pytest.mark.parametrize("failures,attempts,success", [(2, 3, True), (3, 2, False)])
def test_database_startup_retry_budget(monkeypatch, failures, attempts, success):
    calls = []

    def initialize(*, deadline):
        assert deadline > 0
        calls.append(True)
        if len(calls) <= failures:
            raise psycopg2.OperationalError("test database not ready")

    monkeypatch.setattr(main, "init_db", initialize)
    monkeypatch.setenv("DB_STARTUP_ATTEMPTS", str(attempts))
    monkeypatch.setenv("DB_STARTUP_DELAY_SECONDS", "0")

    async def start():
        async with main.lifespan(main.app):
            assert len(calls) == failures + 1

    if success:
        asyncio.run(start())
    else:
        with pytest.raises(psycopg2.OperationalError):
            asyncio.run(start())
        assert len(calls) == attempts


@pytest.mark.parametrize(
    "attempts,delay,timeout",
    [
        ("0", "1", "180"),
        ("1", "-1", "180"),
        ("1", "nan", "180"),
        ("1", "inf", "180"),
        ("1", "0", "0"),
        ("1", "0", "1"),
        ("1", "0", "nan"),
        ("1", "0", "inf"),
        ("bad", "0", "180"),
    ],
)
def test_invalid_startup_configuration(monkeypatch, attempts, delay, timeout):
    monkeypatch.setenv("DB_STARTUP_ATTEMPTS", attempts)
    monkeypatch.setenv("DB_STARTUP_DELAY_SECONDS", delay)
    monkeypatch.setenv("DB_STARTUP_TIMEOUT_SECONDS", timeout)

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("Invalid startup configuration was accepted")

    with pytest.raises(ValueError):
        asyncio.run(start())


def test_startup_deadline_bounds_retry_delay(monkeypatch):
    calls, sleeps = [], []
    remaining = iter([10000, 1000])

    def budget(deadline):
        try:
            return next(remaining)
        except StopIteration:
            raise TimeoutError("Startup budget exhausted") from None

    def initialize(*, deadline):
        calls.append(True)
        raise psycopg2.OperationalError("Database not ready")

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(main, "_startup_remaining_ms", budget)
    monkeypatch.setattr(main, "init_db", initialize)
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setenv("DB_STARTUP_ATTEMPTS", "30")
    monkeypatch.setenv("DB_STARTUP_DELAY_SECONDS", "10")

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("Startup should time out")

    with pytest.raises(TimeoutError):
        asyncio.run(start())
    assert len(calls) == 1 and sleeps == [1]


def test_startup_does_not_retry_schema_permission_errors(monkeypatch):
    calls = []

    def initialize(*, deadline):
        calls.append(True)
        raise psycopg2.ProgrammingError("Permission denied")

    monkeypatch.setattr(main, "init_db", initialize)

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("Invalid schema permissions must fail startup")

    with pytest.raises(psycopg2.ProgrammingError):
        asyncio.run(start())
    assert len(calls) == 1


def test_elapsed_startup_budget_prevents_connecting(monkeypatch):
    monkeypatch.setattr(main, "get_db_connection", lambda **kwargs: pytest.fail("Must not connect"))
    with pytest.raises(TimeoutError):
        main.init_db(deadline=main.time.monotonic() - 1)


def test_cloud_sql_socket_dsn_is_passed_to_psycopg2(monkeypatch):
    dsn = "host=/cloudsql/course:us-central1:cra-pg dbname=cra_phase3 user=cra_app"
    captured = {}

    def connect(value, **kwargs):
        captured.update(dsn=value, **kwargs)
        return "connection"

    monkeypatch.setattr(main, "DB_URL", dsn)
    monkeypatch.setattr(main.psycopg2, "connect", connect)
    assert main.get_db_connection() == "connection"
    assert captured["dsn"] == dsn and captured["connect_timeout"] == 5
    assert captured["options"] == "-c timezone=UTC"
