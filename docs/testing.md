# Phase 3 verification record

## Baseline — 2026-10-17

- Repository base: `99147b3bf9e2f1c02f54bd017a126b66e776fef3`.
- Original service read-only probes: `/openapi.json` returned 200; unknown release returned 404 with the contract error envelope.
- The original database contained one release, zero components, and no clock override.
- The old suite begins with a destructive reset. To preserve existing project data,
  its four unchanged tests ran against an isolated copy of the exact running image
  (`sha256:1b4d29d860ffbeb65b4522c2d3a9e46ab72df651f39385561e0c7fbc00e4aa9a`)
  on `http://127.0.0.1:18080/api/v1`, backed by a separate disposable PostgreSQL
  database. Only the test module's BASE_URL was overridden in memory.
- Result: **4 passed, 0 failed**, 0.44 seconds. JUnit: `artifacts/baseline.xml`.
- These tests have incomplete AC coverage and their one-component success fixture
  omits required CycloneDX `type`; baseline success does not prove Phase 3 completion.
- No original database reset, volume deletion, remote deployment, or commit occurred.

Subsequent stage results are appended after actual execution.

## REQ-01 stage

- Changed `cra-service/main.py`: explicit request string/date validation,
  nonempty release user header, informative 400 messages, UTC clock normalization,
  inclusive UTC support-date reads, preserving release-column widening to TEXT.
- Existing suite against the isolated API: **4 passed, 0 failed**, 0.30 seconds
  (`artifacts/stage-req01-existing.xml`).
- Additional HTTP checks: **36 passed, 0 failed**
  (`artifacts/stage-req01-checks.json`), including shared AC-01 requests/reads,
  rejected-request retry, rollover, invalid types/dates, header validation,
  duplicate handling, long strings, and timezone-aware clock normalization.
- Empty product/version behavior remains unchanged pending pod agreement.
- The original application's data and containers were not modified.

## REQ-02 stage

- Added offline strict CycloneDX validation, transaction cleanup, and per-release
  replacement locking; updated the dependency manifest and Docker copy step.
- The shared SBOM independently passed the packaged strict 1.6 validator.
- Targeted HTTP checks: **14 passed, 0 failed** (`artifacts/stage-req02-checks.json`).
- Old suite: **3 passed, 1 failed** (`artifacts/stage-req02-old-suite.xml`):
  `test_ac_02_sbom_ingestion` used an invalid component without `type` and now
  correctly receives 400. This test defect is corrected in the next stage.
- A temporary isolated-database trigger forced the final INSERT to fail. All
  25 prior components survived and no idle transactions remained. The first probe
  exposed connection reuse after an unhandled SQL exception; adding a database
  exception handler and repeating the complete probe passed with a JSON 500.
  The temporary trigger/function were removed.
- Packaged JSON validators cover 1.2–1.7; this is a library capability, not a new
  pod agreement. Existing top-level normalization/rejection policies are retained.
- Original database still: one release, zero components, clock unset.

## Acceptance-suite stage

- Replaced the old incomplete tests and added `conftest.py` / development dependencies.
- Actual run on the isolated Docker API: **60 passed, 0 failed**, 6.22 seconds
  (`artifacts/stage-acceptance.xml`).
- Tests load the shared fixtures unchanged, validate response schemas/formats from
  `docs/openapi.yaml`, and cover AC-01/02/03 success, rejection, and boundaries.
- Additional cases cover atomic replacement, repeat uploads, concurrent replacements,
  required user headers, invalid clock preservation, unknown releases, and reset.
- `BASE_URL` / `--base-url` configure the target. `--allow-reset` is mandatory;
  never pass it for another team's service without prior coordination.
- Clock validation's existing 400 response is recorded as undocumented by OpenAPI.

## Startup and test-configuration stage

- Added bounded lifespan initialization/retries, DB/API health checks,
  environment-based configuration and structured request logs. Importing the
  module does not connect to the database.
- Added `docker-compose.test.yml` with its own named PostgreSQL volume, no
  published DB port, and API on loopback port 18080. It never uses the original
  `cra-service_pgdata` volume. Main Compose now binds DB access to loopback.
- Rebuilt/started that stack with Compose `--wait`: both services healthy.
- HTTP suite: **60 passed, 0 failed**, 8.63 seconds (`artifacts/stage-startup.xml`).
- Startup retry/configuration tests: **4 passed, 0 failed**, 0.70 seconds
  (`artifacts/stage-startup-unit.xml`). A dateutil deprecation warning occurs on
  the Windows Python 3.12 runner; the service remains on Python 3.11.
- Saved a release and 25-component snapshot, normally restarted both test API
  and PostgreSQL containers, waited for health, and verified exact release/status
  and name/version/purl retention. No volumes were deleted. This is Phase 3
  durability evidence, not full AC-10 completion (incidents/audit are absent).

## Final static checks, regression run and local refresh

- Final run: **67 passed, 0 failed, 0 skipped**, 9.34 seconds
  (`artifacts/final-results.xml`). This includes 63 HTTP cases and 4 startup
  cases. One third-party dateutil deprecation warning remains on the Windows
  Python 3.12 test runner; the API runs Python 3.11 in Docker.
- Ruff lint/format checks passed across service and check scripts; mypy passed
  on both service source modules. Shared OpenAPI 3.1 validation passed. The
  shared SBOM validates and matches every source lock-file name/version pair.
- Added explicit API response models and accurate generated 400 documentation,
  without changing the shared YAML. Both running generated OpenAPI documents
  validate and contain the six implemented operations, without default 422s.
- The repeatable internal `scripts/check_local_rollback.py` check passed inside
  the isolated test API: forced final INSERT failure, all 25 prior components
  retained, JSON 500, zero idle transactions, trigger/function removed afterward.
  CI runs this separately from portable cross-team HTTP checks.
- GitHub Actions configuration is present, but no hosted CI run or branch
  protection change occurred. Actual verification above was local.
- Refreshed the local application with the tested source using its existing
  credentials in an ignored `.env`. Both `cra_api` and `cra_postgres` are healthy.
  Application URL: `http://localhost:8080`; isolated tests: `http://127.0.0.1:18080`.
- Original volume remains `cra-service_pgdata`. Before/after row fingerprints
  match exactly for releases, components and test clock: **1 / 0 / 0 rows**.
  Artifacts: `original-preservation-before.json` and `original-preservation-after.json`.
  No reset was sent to the original application. PostgreSQL now binds only to
  `127.0.0.1:5432`.
- Running application image ID:
  `sha256:47acb1ac62a022c695cfdb89f6e0a588d57e7705f63ced3352c02daf97573068`.
  Source version is base `99147b3` plus the uncommitted working-tree changes;
  runtime/source hashes are saved under `artifacts/`. No new commit/tag exists.
- Read-only smoke checks on both ports passed: valid OpenAPI, unknown-release
  404/error envelope and request ID. Timestamped request logs were captured in
  `artifacts/local-api.log` with request ID, user, endpoint, status and duration.
- Protected contract/fixture hashes match their pre-edit values. Removed the
  tracked generated pytest bytecode and added ignore/implementation line-ending
  rules. No named Docker volume was deleted. Temporary baseline containers and
  their private network were removed; the application and final test stacks remain.
- No remote deployment, class registry update, cross-team execution, commit or
  push occurred. Open pod decisions and Phase 3 delivery gaps remain in
  `decisions.md` / `phase3_status.md`; Phase 4/5 features remain absent.
