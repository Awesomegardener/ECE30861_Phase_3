"""Report polling cannot transiently reject a new run as already running."""

from contextlib import contextmanager

from autograder.store import Store


def test_ready_and_completed_report_reads_do_not_take_execution_lock(monkeypatch):
    store = Store("unused")

    class Connection:
        @contextmanager
        def cursor(self):
            yield self

        def execute(self, *args):
            raise AssertionError("Ordinary read tried to acquire execution lock")

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(store, "connection", connection)
    for report in (
        None,
        {"running": False, "status": "ready"},
        {"running": False, "status": "completed"},
    ):
        monkeypatch.setattr(store, "get", lambda *args: report)
        assert store.read("tester") == report
