"""The opt-in adapter must never reset a different database accidentally."""

from contextlib import contextmanager

import main
import pytest
from autograder.config import HarnessError


@pytest.fixture
def adapter_database(monkeypatch):
    queries = []

    class Cursor:
        def execute(self, query, parameters=None):
            queries.append((query, parameters))

        def fetchone(self):
            return {"name": "cra_grading"}

    class Connection:
        @contextmanager
        def cursor(self):
            yield Cursor()

    @contextmanager
    def database():
        yield Connection()

    monkeypatch.setattr(main, "database", database)
    return queries


@pytest.mark.parametrize(
    "database_name", ["", "retained_database", "cra_db", "cra_test", "postgres", "cra_grading_typo"]
)
def test_adapter_reset_refuses_unapproved_database(adapter_database, database_name):
    with pytest.raises(HarnessError) as error:
        main.autograder_reset(None, database_name)
    assert error.value.status == 503
    assert not any("TRUNCATE" in query or "DELETE" in query for query, _ in adapter_database)


def test_adapter_reset_and_clock_use_one_transaction(adapter_database):
    clock = main.ClockUpdate(now="2026-11-01T23:59:59Z").now
    main.autograder_reset(clock, "cra_grading")
    assert [query for query, _ in adapter_database] == [
        "SELECT current_database() AS name",
        "TRUNCATE releases CASCADE",
        "DELETE FROM test_clock",
        "INSERT INTO test_clock (id, now) VALUES (1, %s)",
    ]
    assert adapter_database[-1][1] == (clock,)


def test_run_rechecks_database_authorization(adapter_database):
    with pytest.raises(HarnessError):
        main.autograder_verify_database("retained_database")
    main.autograder_verify_database("cra_grading")
    assert len(adapter_database) == 2


def test_adapter_refuses_a_course_database_even_when_its_name_is_explicitly_approved(monkeypatch):
    @contextmanager
    def retained_database():
        pytest.fail("Dedicated database policy should reject this before connecting")
        yield

    monkeypatch.setattr(main, "database", retained_database)
    with pytest.raises(HarnessError):
        main.autograder_reset(None, "cra_db")
