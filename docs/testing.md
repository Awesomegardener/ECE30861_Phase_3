# Phase 3 verification record

This is a chronological record. Statements about uncommitted code or missing CI
in earlier entries describe that stage; current CI and clock/evidence results are
recorded at the end. Public deployment and cross-team tests remain unverified.

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

## Verified GitHub Actions run

- Branch: `phase3-improvements`; commit: `2a95313d524e07072bead8eff0b6ea3035e2ecf8`.
- [Run 39082032962](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39082032962)
  completed successfully on 2026-10-18 at approximately 00:15 UTC.
- Job logs were inspected: **67 passed in 6.72 seconds**, on Linux/Python 3.11.17.
  Ruff, formatting, mypy, shared OpenAPI/fixture validation, Docker startup and
  the forced-insert SQL rollback check passed.
- The `phase3-results` artifact was uploaded. This is CI-stack verification, not
  public deployed-service verification. The workflow did not deploy the service.
- GitHub reported `main` and `phase3-improvements` as unprotected during review.
  No branch protection, merge or deployment settings were changed.

## Clock validation and HTTP evidence increment

At the time of this local verification, the following changes were uncommitted
work based on `2a95313`. They are not covered by the initial hosted run above;
later commits require their own CI run evidence.

- Added an RFC 3339 syntax gate before the existing aware-datetime/calendar
  parser. Numeric strings, space/underscore separators, missing seconds,
  malformed offsets, invalid calendars/times and surrounding whitespace are
  rejected with the existing 400 `INVALID_REQUEST` response. No shared error
  status or literal-`Z` policy was changed.
- Valid numeric offsets (including non-hour offsets), uppercase/lowercase
  `T`/`Z`, fractional seconds, UTC date rollover and leap-day inputs are tested.
  Existing Python/PostgreSQL microsecond precision and datetime representation
  limits remain unchanged. Leap-second timestamps remain unsupported by the
  existing datetime parser; no new conversion semantics were introduced.
- First focused run: 45 passed, 1 failed because the optional JSON-schema format
  checker accepts a final LF. Corrected that test-oracle assumption; explicit
  trailing-newline rejection remains covered. The focused clock/startup run then
  passed **46 tests**. Clock/evidence/startup checks then passed **53 tests**.
- Full run against a newly created Docker project, `cra-phase3-clock-evidence`,
  API `http://127.0.0.1:18081`: **153 passed, 0 failed, 0 skipped**, 15.28 seconds.
  Counts: 100 HTTP, 42 clock-model, 7 evidence and 4 startup tests.
- The full Windows/Python 3.12 runner reported three warnings: the existing
  dateutil deprecation and two pytest-cache permission warnings. They did not
  fail tests; the Docker API uses Python 3.11.
- Ruff lint/format checks passed across 10 Python files; mypy passed on both
  service modules. Shared OpenAPI 3.1 validation and all 25 fixture/lock-file
  pairs passed. Shared inputs and SBOM normalization remain unchanged.
- The internal rollback check passed in the fresh stack: forced final INSERT
  failure, 25 previous components retained, JSON 500, no idle transactions.
- Evidence: `artifacts/clock-evidence/results.xml`, `sql-rollback.txt`,
  `compose.log`, `docker-provenance.json`, operation status and input hashes.
  The HTTP bundle is
  `http-evidence-20261018T004450978497Z-e01764c9.json` in that directory.
  It contains **519 exchanges**, including 27 AC-03 rejection examples and both
  concurrent replacement uploads. No captured body was truncated. An explicit
  check found no local private database password in the bundle.
- The fresh API image's runtime `main.py`, `sbom_validation.py` and requirements
  hashes match the tested working files; image/source provenance is saved with
  the evidence. The supplied SHA identifies the base commit, not a claim that
  these uncommitted changes already exist in GitHub.
- Existing databases were fingerprinted before testing. No test request targeted
  ports 8080 or 18080; the full suite reset only the newly created test database.
  Final comparison passed: all four existing container IDs/images/mounts and
  both databases' row counts/hashes match their before-test snapshots. The
  application retains 1 release / 0 components / 0 clock rows; the older test
  database retains 2 / 25 / 0. Snapshots are
  `artifacts/clock-evidence-preservation-before.json` and `...-after.json`.
- The fresh test API/database containers were stopped after verification; their
  named volume and test data were retained. The four pre-existing containers
  remain healthy. No application refresh, remote deployment, commit or push was
  performed for this increment.

### Capture and interpret evidence

Add these options to a coordinated HTTP test run:

```powershell
.\.venv\Scripts\python.exe -B -m pytest cra-service/test_api.py --base-url http://127.0.0.1:18081 --allow-reset --capture-http-bodies --tested-commit 2a95313d524e07072bead8eff0b6ea3035e2ecf8 --evidence-dir artifacts/report-run --junitxml=artifacts/report-run/results.xml
.\.venv\Scripts\python.exe -B scripts/check_contract.py --evidence-dir artifacts/report-run
```

The HTTP target must be an isolated/coordinated test service. For a remote
service, substitute its actual deployed full SHA (or `TESTED_COMMIT_SHA`) rather
than the runner's checkout SHA. Omit the option if unknown. Target SHA is
operator-supplied; the runner does not verify deployment provenance. For an
uncommitted local image, retain the image/source hashes alongside the base SHA.

Each run creates a unique `http-evidence-<UTC>-<id>.json`. The bundle includes:

- `run`: target base URL, supplied target SHA or null, version provenance,
  runner commit/dirty state/source hashes, shared-input hashes and start/end UTC.
- `exchanges`: pytest test ID, method, contract path, actual request URL, status,
  duration, UTC request/response times, documented-status flag and schema result.
- Opt-in request/response bodies, preserving JSON, malformed text, and empty 204
  responses. `--evidence-body-limit` defaults to 65,536 characters per body;
  oversized values are explicitly marked truncated and retain byte count/hash.
- Only content type, test user ID and request ID headers are retained. URL user
  credentials/query values and common sensitive JSON keys are redacted. Capture
  only synthetic fixtures and review artifacts before publication; redaction
  cannot identify arbitrary confidential free text.

Bodies are off by default. Failed response-schema checks and transport failures
are retained, and session teardown writes evidence even when tests fail.
Concurrent uploads use separate HTTP sessions and are also recorded.
`operation-observations.json` is overwritten as a latest-run convenience; unique
bundles retain earlier runs. Use separate evidence directories per target/run and
pass the same directory to the contract-report script.

Pair bundles with JUnit: `schema_validation=passed` does not prove all business
assertions passed, and `documented=false` still identifies the shared clock
operation's missing 400 response. These files do not establish human AC-03
review, server code coverage, public availability or cross-team completion.

RFC syntax reference used for this fix:
https://www.rfc-editor.org/rfc/rfc3339.html#section-5.6.
