# ECE 30861 — Phase 3 CRA service

FastAPI + PostgreSQL + Docker release registration and CycloneDX JSON component
ingestion. The authoritative interface is [`docs/openapi.yaml`](docs/openapi.yaml);
it and [`fixtures/`](fixtures/) are unchanged. No Phase 4/5 features are implemented.

## Start the application

Requires Docker Desktop with Linux containers. From `cra-service/`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env: use the CURRENT password if reusing an existing database volume.
docker compose up --build -d --wait
docker compose ps
docker compose logs --tail 30 api
```

For an existing `.env`, edit it rather than overwriting it. Configuration is
ignored by Git. Creating `.env` does not rotate a database password. For passwords
containing URL-special characters, configure an appropriately encoded
`DATABASE_URL` as described in `.env.example`.

Application: `http://localhost:8080`; generated docs: `/docs`. PostgreSQL uses
the existing `pgdata` named volume and is bound to loopback. Schema initialization
widens existing string columns without deleting records. Normal API/DB restarts
retain data. Do not delete the database volume to upgrade the application.

## Run tests without clearing application data

The HTTP suite calls `/test/reset`. Use the dedicated test stack, which has a
different Compose project and named volume. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r cra-service/requirements-dev.txt
docker compose -f cra-service/docker-compose.test.yml up --build -d --wait
.\.venv\Scripts\python.exe -B -m pytest cra-service --base-url http://127.0.0.1:18080 --allow-reset --junitxml=artifacts/results.xml
.\.venv\Scripts\python.exe scripts/check_contract.py
```

For the internal SQL-failure regression check, run only inside the dedicated stack:

```powershell
Get-Content -Raw scripts/check_local_rollback.py | docker compose -f cra-service/docker-compose.test.yml exec -T api python -
```

It requires the dedicated `cra_test` database, injects a temporary failure, verifies
rollback and connection cleanup, then removes its trigger/function. It is not a
cross-team interface test. CI runs the same check with standard input redirection.

On Linux use `.venv/bin/python`. The runner accepts `BASE_URL` or `--base-url`,
with a server root or `/api/v1` suffix. Fixture paths resolve relative to the
repository, not the working directory. Every HTTP test resets its target and
fixes the UTC clock. `--allow-reset` is required; coordinate before targeting
another team's deployment. Do not select a database whose data must be retained.

To stop the test stack while retaining its separate volume:

```powershell
docker compose -f cra-service/docker-compose.test.yml down
```

`fixtures/sbom_source/` describes the test product, not service dependencies.
Normal tests consume the agreed SBOM unchanged; they do not regenerate it or
contact vulnerability services.

## Static checks and CI

```powershell
.\.venv\Scripts\python.exe -m ruff check cra-service scripts
.\.venv\Scripts\python.exe -m ruff format --check cra-service scripts
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe scripts/check_contract.py
```

GitHub Actions runs these checks and the Docker HTTP/startup suite on Python 3.11,
then uploads results/logs. A hosted CI run requires a later approved push. Merge
blocking also depends on branch protection, which has not been changed.

Ignored local `artifacts/` outputs include JUnit results, response observations,
status JSON for all 17 contract operations, and protected-input hashes. Responses
are checked against shared OpenAPI 3.1 schemas, including date formats.

## Scope and evidence

- [Executed stage results](docs/testing.md)
- [AC mapping, operation status and delivery tasks](docs/phase3_status.md)
- [Open pod decisions](docs/decisions.md)
- [Implemented architecture and data model](docs/models.md)

The shared fixture establishes the 25-component success case. Pending decisions
include empty product/version values, supported CycloneDX versions, missing
component versions, empty-document behavior, nested inventory counting,
clock-input policy, exact errors, and reset defaults. Nested content is schema
validated but storage remains top-level-only pending agreement. Phase 3 completion
must not be claimed while this parsing risk remains unresolved.

No remote deployment URL, registry update or two-way Team 2 result is verified.
Those require approved hosting and coordinated testing.
