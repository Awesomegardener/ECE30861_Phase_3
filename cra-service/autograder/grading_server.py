"""Single-worker instrumented Cloud Run entrypoint. No filesystem persistence."""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path


def configure_preparation(service):
    """Keep grading controls reachable before domain resources are ready.

    The ordinary production lifespan is unchanged. Grading setup initializes
    schema on demand, after checking the existing disposable database identity.
    It does not provision cloud resources or bypass the reset authorization.
    """
    harness = service.app.state.autograder
    reset = harness.reset

    def prepare(now, approved_database):
        service.autograder_verify_database(approved_database)
        service.init_db(deadline=time.monotonic() + harness.settings.setup_timeout)
        reset(now, approved_database)

    @asynccontextmanager
    async def controls_lifespan(application):
        try:
            yield
        finally:
            service.shutdown_children()

    harness.reset = prepare
    service.app.router.lifespan_context = controls_lifespan


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

    from .live_coverage import SessionCoverage

    configure_preparation(service)
    store = service.app.state.autograder.store
    if service.app.state.autograder.settings.coverage_enabled:
        manager = SessionCoverage(collector, root.parent, store)
        manager.install(service.app)
        service.app.state.session_coverage = manager
    uvicorn.run(
        service.app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        workers=1,
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
