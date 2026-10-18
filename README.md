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
serializes concurrent starts and widens existing string columns only when needed,
without deleting records. Normal API/DB restarts
retain data. Do not delete the database volume to upgrade the application.

Operational health: `/health/live` returns 200 without querying PostgreSQL;
`/health/ready` returns 200 after a short read-only query, or generic 503 when
the database is unavailable. Both omit shared API schemas. Docker uses `PORT`
when provided and defaults to 8080; the existing Compose mappings stay unchanged.

## Run tests without clearing application data

The HTTP suite calls `/test/reset`. Use the dedicated test stack, which has a
different Compose project and named volume. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r cra-service/requirements-dev.txt
docker compose -f cra-service/docker-compose.test.yml up --build -d --wait
$testedCommit = (git rev-parse HEAD).Trim()
.\.venv\Scripts\python.exe -X utf8 -B -m pytest cra-service --base-url http://127.0.0.1:18080 --allow-reset --capture-http-bodies --tested-commit $testedCommit --evidence-dir artifacts/local --junitxml=artifacts/local/results.xml
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/local
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
Use `-X utf8` on Windows: the installed CycloneDX validator opens its packaged
schemas using Python's default text encoding, which may otherwise be a legacy
locale. Docker/CI use UTF-8 environments.

To stop the test stack while retaining its separate volume:

```powershell
docker compose -f cra-service/docker-compose.test.yml down
```

`fixtures/sbom_source/` describes the test product, not service dependencies.
Normal tests consume the agreed SBOM unchanged; they do not regenerate it or
contact vulnerability services.

## Save Phase 3 report evidence

Each HTTP run writes a separate `http-evidence-<UTC>-<id>.json` file. It records
the target URL, operator-supplied target SHA, runner SHA/dirty state, source and
shared-input hashes, UTC request/response times, test IDs, statuses, schema-check
results, and request IDs. `--capture-http-bodies` includes bounded, redacted JSON
or text bodies, including malformed input and rejected responses. Bodies are
omitted by default; use synthetic fixtures and inspect evidence before sharing.

For another team's service, pass its actual deployed full SHA with `--tested-commit`
or `TESTED_COMMIT_SHA`; the runner cannot independently verify that deployment's
version. If unknown, omit it and the evidence explicitly records an unknown target
version. The local example above uses the checkout's HEAD; an uncommitted Docker
build also needs its dirty-state/source hashes and image identifier, rather than
being described as exactly that committed version. See [the evidence format and
executed results](docs/testing.md#clock-validation-and-http-evidence-increment).

Use a different `--evidence-dir artifacts/<target-and-run>` for each target.
Individual evidence bundles are retained; `operation-observations.json` is a
latest-run convenience. Pass the same directory to `scripts/check_contract.py`.
The JUnit report records test outcomes; a passed response-schema check alone does
not establish that every acceptance assertion passed. Human AC-03 review and
deployed-service verification must be recorded separately.

## Static checks and CI

```powershell
.\.venv\Scripts\python.exe -m ruff check cra-service scripts
.\.venv\Scripts\python.exe -m ruff format --check cra-service scripts
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_contract.py
```

GitHub Actions runs these checks and the Docker suite on Python 3.11, then uploads
results/logs. The [main run for baseline commit `f27cfd5`](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39157992256)
was verified successful. The deployment-readiness increment passes **291 local
tests**, including 157 HTTP tests against a fresh Docker stack, plus real
concurrent schema initialization, container PORT, DB-outage/recovery, restart
persistence, graceful-shutdown and nested-insert rollback checks. See
`docs/testing.md` for counts, commands, evidence and limits. The updated workflow
runs those Docker checks too, but has not run on GitHub for this uncommitted
increment; the baseline run does not cover it.
The workflow captures synthetic HTTP bodies and the checkout SHA. Merge blocking
depends on branch protection; both branches were reported unprotected during an
earlier review, and that setting was not changed here.

Ignored local `artifacts/` outputs include JUnit results, response observations,
status JSON for all 17 contract operations, and protected-input hashes. Responses
are checked against shared OpenAPI 3.1 schemas, including date formats.

## Scope and evidence

- [Executed stage results](docs/testing.md)
- [AC mapping, operation status and delivery tasks](docs/phase3_status.md)
- [Open pod decisions](docs/decisions.md)
- [Implemented architecture and data model](docs/models.md)
- [Google Cloud Console deployment guide](docs/deployment-google-cloud.md)

The unchanged shared fixture establishes the 25-component success case. The
implementation accepts CycloneDX 1.4/1.5/1.6, validates the whole document and
flattens root inventory descendants at every depth. Every inventory component
must have a string version. Counts and storage retain repeated valid occurrences;
metadata/tool subtrees are excluded. Identical sibling entries still fail the
official schemas' uniqueness constraint. Replacement remains transactional.

The user supplied Team 6 questions and Team 2 acceptance/recommendations. Final
Team 6 acknowledgement of metadata/tool exclusion, occurrence retention and the
wider exact-code testing policy is not documented. These implementation choices
are not a newly approved shared contract; see `docs/decisions.md`. Open questions
also include empty release strings, absent inventory arrays, clock/error details
and reset defaults. Exact error assertions are limited to explicit missing-header
`INVALID_REQUEST` and unchanged shared-fixture expectations; other errors need the
contract envelope, expected status and meaningful nonempty reason.

Google Cloud Run plus Cloud SQL PostgreSQL is the selected hosting plan, using
`main`. No remote deployment URL, cloud resources, registry update or two-way Team 6
result is verified. PORT, startup and health improvements are verified locally.
The Console guide covers Cloud SQL sockets, secrets, IAM, costs, probes, hosted
verification and rollback. Root `cloudbuild.yaml` builds/publishes an image only
when run by an authorized operator; it does not deploy. Cloud configuration,
spending and deployment still require approval and coordinated testing.
