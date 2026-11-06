"""Single-worker instrumented Cloud Run entrypoint. No filesystem persistence."""

import os
from pathlib import Path


def main():
    import coverage
    import uvicorn

    root = Path(__file__).resolve().parents[1]
    # Must precede importing main or creating the sync worker pool.
    files = (
        "main.py",
        "sbom_validation.py",
        "timestamps.py",
        "phase4.py",
        "purl_matching.py",
        "osv_source.py",
    )
    collector = coverage.Coverage(
        data_file=None, branch=True, config_file=False, include=[str(root / name) for name in files]
    )
    collector.start()
    import main as service

    from .live_coverage import LiveCoverage

    settings = service.app.state.autograder.settings
    store = service.app.state.autograder.store

    def session_running(role, identifier):
        with store.connection() as conn:
            report = store.get(conn, role, identifier)
        return bool(report and report.get("running"))

    manager = LiveCoverage(
        collector,
        root.parent,
        settings,
        service.autograder_verify_database,
        session_running=session_running,
    )
    manager.install(service.app)
    service.app.state.live_coverage = manager
    uvicorn.run(
        service.app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        workers=1,
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
