"""A reset after INSERT commit must not change a successful creation response."""

import datetime
from contextlib import contextmanager

import main
import psycopg2
import pytest


@pytest.fixture
def release_database(monkeypatch):
    state = {
        "row": None,
        "clock": None,
        "commits": 0,
        "rollbacks": 0,
        "reset_after_commit": True,
        "clock_error": False,
        "commit_error": False,
    }

    class Cursor:
        def execute(self, query, params=None):
            if query.startswith("INSERT INTO releases"):
                state["row"] = dict(
                    zip(("release_id", "product", "version", "support_end_date"), params)
                )
                self.result = state["row"].copy()
            elif query.startswith("SELECT * FROM releases"):
                self.result = state["row"]
            elif query.startswith("SELECT now FROM test_clock"):
                if state["clock_error"]:
                    raise psycopg2.OperationalError("Injected clock query failure")
                self.result = {"now": state["clock"]} if state["clock"] else None
            else:
                pytest.fail(f"Unexpected SQL: {query}")

        def fetchone(self):
            return self.result

    class Connection:
        @contextmanager
        def cursor(self):
            yield Cursor()

    @contextmanager
    def database():
        before = state["row"]
        try:
            yield Connection()
            if state["commit_error"]:
                raise psycopg2.OperationalError("Injected commit failure")
        except Exception:
            state["row"] = before
            state["rollbacks"] += 1
            raise
        state["commits"] += 1
        if state["reset_after_commit"] and state["commits"] == 1:
            # Another request commits a reset in the gap before response construction.
            state["row"] = None
            state["clock"] = None

    monkeypatch.setattr(main, "database", database)
    return state


@pytest.mark.parametrize(
    "clock,end_date,expected",
    [
        ("2026-11-01T23:59:59.123456+02:00", "2026-11-01", "supported"),
        ("2026-11-02T00:30:00+02:00", "2026-11-01", "supported"),
        ("2026-11-01T23:30:00-02:00", "2026-11-01", "unsupported"),
        (None, "2099-01-01", "supported"),
    ],
)
def test_create_response_survives_reset_after_commit(release_database, clock, end_date, expected):
    release_database["clock"] = datetime.datetime.fromisoformat(clock) if clock else None
    release = main.ReleaseCreate(product="RaceRouter", version="1", support_end_date=end_date)
    result = main.create_release(release, x_user_id="race-test")

    assert result == {
        "release_id": result["release_id"],
        "product": "RaceRouter",
        "version": "1",
        "support_end_date": end_date,
        "support_status": expected,
    }
    assert result["release_id"].startswith("rel-")
    assert release_database["commits"] == 1
    assert release_database["row"] is None and release_database["clock"] is None


def test_create_rolls_back_when_clock_query_fails(release_database):
    release_database.update(clock_error=True, reset_after_commit=False)
    release = main.ReleaseCreate(product="Rollback", version="1", support_end_date="2026-11-01")
    with pytest.raises(psycopg2.OperationalError):
        main.create_release(release, x_user_id="race-test")
    assert release_database["row"] is None
    assert release_database["commits"] == 0 and release_database["rollbacks"] == 1


def test_create_does_not_report_success_when_commit_fails(release_database):
    release_database["commit_error"] = True
    release = main.ReleaseCreate(product="Rollback", version="1", support_end_date="2026-11-01")
    with pytest.raises(psycopg2.OperationalError):
        main.create_release(release, x_user_id="race-test")
    assert release_database["row"] is None
    assert release_database["commits"] == 0 and release_database["rollbacks"] == 1
