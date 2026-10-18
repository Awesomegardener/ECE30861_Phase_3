"""Startup must tolerate transient DB failures and stop after its retry budget."""

import asyncio

import main
import psycopg2
import pytest


@pytest.mark.parametrize("failures,attempts,success", [(2, 3, True), (3, 2, False)])
def test_database_startup_retry_budget(monkeypatch, failures, attempts, success):
    calls = []

    def initialize():
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


@pytest.mark.parametrize("attempts,delay", [("0", "1"), ("1", "-1")])
def test_invalid_startup_configuration(monkeypatch, attempts, delay):
    monkeypatch.setenv("DB_STARTUP_ATTEMPTS", attempts)
    monkeypatch.setenv("DB_STARTUP_DELAY_SECONDS", delay)

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("Invalid startup configuration was accepted")

    with pytest.raises(ValueError):
        asyncio.run(start())
