# Phase 3 verification record

This is a chronological record. Statements about uncommitted code or missing CI
in earlier entries describe that stage; current CI and policy/test results are
recorded at the end. The October 26 entry distinguishes saved hosted evidence
from local adapter verification and deployment that has not occurred.

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

## Supplied policy and recursive inventory increment (2026-10-18)

Base checkout: `main`, `0c067d85d7977a32409fa3f552a225424a0b83c1`. At the time
of this local verification, the changes were uncommitted. The user supplied
Team 6's questions and Team 2's answers;
approval distinctions and the contract comparison are recorded in `decisions.md`.
No shared YAML or Team 6 fixture edits are part of this increment.

### Executed checks and regressions

- Docker Desktop's engine was initially stopped. It was started for testing.
  The six pre-existing containers and three pre-existing volumes were inventoried
  before creating a test project. Only `cra_api` and `cra_postgres` were running;
  the older test stacks were stopped and were not started/reset/rebuilt.
- Created a new Compose project, `cra-phase3-pod-decisions-20261018`, using the
  unchanged test Compose file, API `http://127.0.0.1:18082`, separate
  `cra-phase3-pod-decisions-20261018_pgdata_test` volume and database `cra_test`.
  No HTTP test targeted the original port 8080 or the prior 18080/18081 stacks.
- Unchanged baseline: **153 passed**, no failures/skips, 18.08 seconds. Evidence:
  `artifacts/pod-decisions/baseline/results.xml` and its unique HTTP bundle.
- Before the validator fix, seven new nesting regressions failed as expected:
  the three-version eight-occurrence case returned only three roots, repeated
  branches returned two parents instead of four occurrences, and a 31-level
  chain returned only its root. Evidence: `regressions-before.xml`.
- After the validator fix: **51 SBOM unit tests passed**. Combined local checks:
  **107 passed** (51 SBOM, 42 clock, 10 evidence, 4 startup).
- Final complete suite: **264 passed, 0 failed, 0 skipped**, 30.34 seconds. Breakdown: **157
  HTTP integration tests against the rebuilt Docker API/PostgreSQL stack** plus
  the 107 local checks above. The Windows runner uses Python 3.12.14 and the
  Docker API uses Python 3.11. The only reported warning is the existing dateutil
  `utcfromtimestamp` deprecation.
- Ruff lint and format checks pass for all 11 Python files; mypy passes both
  service modules. Shared OpenAPI 3.1 validation passes, all 25 SBOM component
  name/version pairs still match the shared lock file, and all 17 shared API
  operations are reported by `scripts/check_contract.py`.
- The isolated SQL rollback probe now fails the **last nested component INSERT**
  after a replacement parent and earlier children have been processed. It
  passes: JSON 500, all 25 prior components preserved, no idle transactions.
  The probe removes its temporary trigger/function and never targets an
  application database. It is separate from portable HTTP test counts.

### Acceptance and policy coverage

| Requirement/policy | Tests and checked outcomes |
|---|---|
| AC-01 / REQ-01 | Existing shared release cases, invalid types, UTC end-of-day/rollover and clock regressions remain passing. |
| AC-02 / REQ-02 | Unchanged shared 25-component fixture still matches exactly and remains release-isolated. `test_ac02_nested_inventory_counts_isolation_and_replacement` checks 1.4/1.5/1.6: eight inventory occurrences, four repeated name/version/purl tuples, excluded metadata/tool trees, idempotent upload, replacement removal and second-release isolation. |
| AC-03 / REQ-02 | Existing malformed JSON/plaintext/schema cases plus empty body, invalid encoding, missing component version, malformed nested arrays and unsupported specVersion. `test_ac03_missing_nested_version_is_atomic` covers three depths, all supported versions and empty/populated inventories. |
| Release-before-body | `test_ac03_unknown_release_precedes_invalid_body` checks 18 invalid-body variants with a valid user header, always 404 and no change to an existing inventory. Missing-header/existence precedence is not newly specified. |
| Supported schema versions | Real packaged schemas are used for 1.4/1.5/1.6. Unsupported 1.2/1.3/1.7/2.0 HTTP cases preserve empty or prior inventory; unit cases include other unsupported/malformed version strings. |
| Required headers / test exemptions | POST release and PUT SBOM missing headers return exactly 400 `INVALID_REQUEST`; empty headers remain rejected. Valid clock-offset requests and reset requests explicitly omit the user header and pass. |
| Error checks | HTTP errors require the shared envelope and a meaningful nonempty message. Exact code checks are limited to missing-header mapping and unchanged shared fixture expectations. Clock tests no longer impose an unagreed exact code. Local runner tests reject empty/whitespace messages but accept another team's unmapped code. |
| Duplicate boundary | Unit tests retain identical versioned occurrences across separate branches and reject identical siblings under the official schemas. Eight-row HTTP inventories retain four matching name/version/purl occurrences rather than deduplicating. |
| Whole-document validation | Excluded metadata is still schema checked; missing metadata/tool versions are not subjected to inventory-only requirements where the declared CycloneDX schema allows their absence. |

### Evidence and preservation

The final report directory is `artifacts/pod-decisions/final/`: JUnit results,
unique HTTP bundles, operation observations/status and protected-input hashes.
Each full run captures **918 HTTP exchanges**, all passing response checks, with
no body truncation. Earlier bundles remain separate; use the latest bundle with
the final JUnit file. The final bundle is
`http-evidence-20261018T185836759080Z-4de1b353.json`; `verification-summary.json`
records its counts and provenance. The supplied target SHA identifies the base checkout;
dirty-state/source hashes and `docker-provenance.json` identify the actual
uncommitted runtime. This is not a claim that the new code is already on GitHub.

Preservation snapshots under `artifacts/pod-decisions/preservation-before.json`
and `preservation-after.json` compare existing container identities/images,
mounts/ports, running states, live table row counts/hashes and original volume
presence. The original database remains **1 release / 0 components / 0 clock
rows**. The original application was not refreshed. Stopped prior test
containers/volumes are retained. Only the newly created test database receives
the reset-based suite and SQL-failure probe; no existing project data is reset
or deleted. Shared-input SHA-256 hashes match the six pre-edit files.
The new test API/database were stopped after log capture, retaining their new
named volume and test data. The original `cra_api` and `cra_postgres` remain
healthy at their existing image versions; this increment did not refresh them.

The committed baseline's [main GitHub Actions run](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39087275607)
was confirmed successful through the GitHub API. It does not verify these
uncommitted changes. No new CI run, cross-team run, public deployment, human AC-03
sign-off or server-coverage measurement is claimed.

To reproduce in a **new, previously unused** isolated Compose project and port:

```powershell
$env:TEST_API_PORT = '18082'
docker compose -p cra-phase3-pod-decisions-20261018 -f cra-service/docker-compose.test.yml up --build -d --wait
.\.venv\Scripts\python.exe -X utf8 -B -m pytest cra-service --base-url http://127.0.0.1:18082 --allow-reset --capture-http-bodies --tested-commit 0c067d85d7977a32409fa3f552a225424a0b83c1 --evidence-dir artifacts/pod-decisions/final --junitxml=artifacts/pod-decisions/final/results.xml
Get-Content -Raw scripts/check_local_rollback.py | docker compose -p cra-phase3-pod-decisions-20261018 -f cra-service/docker-compose.test.yml exec -T api python -
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/pod-decisions/final
docker compose -p cra-phase3-pod-decisions-20261018 -f cra-service/docker-compose.test.yml stop
```

Choose another unused project/port if this one already contains data you want to
keep. `stop` retains the new test volume and data; never add a volume-deletion
flag. `-X utf8` avoids a Windows legacy-encoding failure when the library reads
its packaged schemas. Use the actual target/base SHA and source/image evidence
for subsequent versions. No Google Cloud or local application configuration was
changed for this policy increment.

## Google Cloud deployment readiness

Executed October 18, 2026 on local `main`, base SHA
`f27cfd5a901637525a0bf4dc9dce856fc1fd9903`. These deployment-readiness changes are
**uncommitted/unpushed**. The baseline's [GitHub Actions run](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39157992256)
was independently checked through the GitHub API: completed/success for that exact
SHA. It does not verify the new startup, health, Docker command or CI changes.
No cloud resources, cloud build, deployed URL or hosted verification exists yet.

### Scope and isolation

Both Compose files, shared OpenAPI and five Team 6 fixture/source files are
byte-for-byte unchanged, checked against SHA-256 snapshots. Tests used a new,
previously unused project `cra-phase3-deployment-20261018`, port **18083**, separate
`cra_test` database and `cra-phase3-deployment-20261018_pgdata_test` volume.
Reset-based tests never targeted port 8080 or any earlier stack. Internal schema
checks created three uniquely named databases only within the new test PostgreSQL
instance; those databases were retained, not dropped. Container controls require
an explicit `cra-phase3-deployment-*` project and validate service labels, test
DSN/database and loopback port mappings before stopping anything.

### Actual results

| Check | Result |
|---|---|
| Final full pytest suite | **291 passed, 0 failed, 0 skipped**, 28.71 seconds |
| Portable AC-01/02/03 and HTTP regressions | **157 passed** against the rebuilt Docker API; unchanged shared fixtures |
| Other tests | **134 passed**: SBOM 51, clock 42, evidence 10, startup 15, health 8, deployment-helper 8 |
| Ruff lint / formatting | Passed for all 15 Python files |
| mypy | Passed for both service modules |
| Shared contract / fixture check | OpenAPI 3.1 valid; all 25 component pairs match the source lock file; all 17 contract operations reported |
| Build/workflow YAML | Parsed; correct Dockerfile/context, build-only steps, logging policy and isolated CI project checked locally; not submitted to Google Cloud |
| Real schema integration | All six scenarios below passed on PostgreSQL 16 |
| Real container integration | Default/custom port, invalid PORT, HTTP health outage/recovery, actual cold-start DB retry, API/DB persistence and graceful shutdown passed |
| Existing forced SQL rollback regression | Passed: final nested INSERT failure returns JSON 500, retains all 25 prior components, no idle transactions |
| Preservation | Original eight container identities/images/mounts/ports/running states and four existing volumes preserved; live application table fingerprints identical |

Windows runner: Python 3.12.14; Docker API: Python 3.11. The only pytest warning is
the existing dateutil `utcfromtimestamp` deprecation. New GitHub CI uses Python
3.11 but has not executed for these working-tree changes.

Startup regression coverage checks transient failures, attempt exhaustion, invalid
attempt/delay/timeout configuration, deadline-limited sleep, fail-fast programming
errors, expired budget before connection, and unchanged psycopg2 socket DSN
passing. Health tests verify DB-independent liveness, healthy/unavailable readiness,
generic error bodies, read-only bounded query configuration/resource cleanup,
no-cache headers and exclusion from generated OpenAPI.

`scripts/check_startup_schema.py` passed these real database scenarios:

1. Six concurrent initializers using independent connections on a new empty schema.
2. Legacy VARCHAR-to-TEXT upgrade preserves release, component and clock rows/timestamps.
3. Repeat TEXT startup succeeds while another session holds ACCESS SHARE locks,
   proving unnecessary exclusive ALTER locks are avoided.
4. Contended advisory lock times out within the checked bound; a subsequent
   initializer recovers and preserves rows.
5. Readiness connection settings are read-only, UTC, statement timeout 1 second,
   lock timeout 500 ms, without changing server defaults.
6. Incompatible existing INTEGER product fails for manual review: original row
   preserved, new DDL rolled back and transaction advisory lock released.

The container helper initially failed because a newly published Docker port closed
the HTTP connection before Uvicorn started (`RemoteDisconnected`). It was a runner
retry defect. The helper now retries that transient response; a regression test
passes. Its successful rerun additionally launches an API while the isolated DB
is stopped, observes `database_not_ready`, restarts that DB, and verifies readiness
recovers. It checks stored release/inventory equality after DB and API restarts,
and a custom-port Uvicorn exits with code 0 after SIGTERM. The initial failed
artifact is retained separately; no remaining test failures are known.

### Evidence and data preservation

Ignored `artifacts/deployment-readiness/final/` contains `results.xml`,
`http-evidence-20261018T202652572927Z-1d8db57e.json`, operation observations/status,
`deployment-runtime.json` (explicit passed status and HTTP exchanges),
`deployment-runtime-initial.json`, source/image `docker-provenance.json`, logs and
`verification-summary.json`. The portable HTTP bundle contains **918 exchanges**,
UTC times, statuses, captured bodies and source/shared-input hashes. Earlier unique
bundles are historical; use the named final bundle with the final JUnit file.
The supplied SHA is the base checkout, not a claim that the dirty image is exactly
that committed release. Image ID is
`sha256:7b08d738c6d1b334f5784ef156d15a60acbc376fcbe2ef795b62481c3ccb9f02`;
runtime `main.py`, validator and requirements bytes match the local sources.

Before/after preservation and protected-input snapshots are one directory above
`final/`. The original application still has **1 release / 0 components / 0 clock
rows**, with identical row hashes. Its API and PostgreSQL containers remain on
their original images and are not refreshed. Previous stopped test stacks remain
stopped. The new test containers are stopped after collecting logs, retaining
their new volume, databases and synthetic records; no volumes/databases are deleted.
No generated evidence, passwords, `.env` or environment files are intended for Git.

### Reproduce locally in a fresh project

Choose another unused project and port if these already contain data to retain.
These commands intentionally change/reset only the new isolated test data:

```powershell
$testProject = 'cra-phase3-deployment-REPLACE_WITH_UNIQUE_LOWERCASE_SUFFIX'
$env:TEST_API_PORT = '18084'
docker compose -p $testProject -f cra-service/docker-compose.test.yml up --build -d --wait --wait-timeout 240
$testedBase = (git rev-parse HEAD).Trim()
.\.venv\Scripts\python.exe -X utf8 -B -m pytest cra-service --base-url http://127.0.0.1:18084 --allow-reset --capture-http-bodies --tested-commit $testedBase --evidence-dir artifacts/deployment-readiness/new-run --junitxml=artifacts/deployment-readiness/new-run/results.xml
Get-Content -Raw scripts/check_startup_schema.py | docker compose -p $testProject -f cra-service/docker-compose.test.yml exec -T api python -
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_deployment_runtime.py --project $testProject --evidence-dir artifacts/deployment-readiness/new-run
Get-Content -Raw scripts/check_local_rollback.py | docker compose -p $testProject -f cra-service/docker-compose.test.yml exec -T api python -
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/deployment-readiness/new-run
docker compose -p $testProject -f cra-service/docker-compose.test.yml stop
```

Docker must be on PATH, or pass its absolute path with `--docker` to the runtime
helper. Replace the project suffix with lowercase letters/digits/hyphens. Run the
README static commands too. CI mirrors the Docker checks using a fresh
`cra-phase3-deployment-ci` project, captures logs/evidence, then removes only its
ephemeral containers/network without deleting volumes. The startup script requires
database-creation privileges available only in the isolated test instance; the
proposed Cloud SQL runtime user deliberately lacks that privilege. These internal
scripts are not appropriate for a deployed service or another team's DB.

The [Console guide](deployment-google-cloud.md) lists remaining gates: approve
project/budget/public test exposure, review/save the code and verify its own CI,
build the reviewed SHA, configure IAM/SQL attachment/secret/probes, then run hosted
HTTPS tests and persistence checks. Human AC-03 review and two-way Team 6 readiness
tests are separate evidence still to collect. Local SQL connectivity tests do not
verify Google-managed IAM, sockets, health routing or availability.

## Release creation / concurrent reset investigation

Investigation base: `7686edf2bbc007ca11c4f284d7e547821488f562` on `main`.
The fix and tests described here are uncommitted, unpushed and not deployed.
No request was sent to the public service during this investigation.

### Supplied hosted evidence

The preserved `artifacts/google-cloud/results.xml` reports **156 passed / 1 failed**
out of 157 HTTP tests, 144.972 seconds (JUnit suite time). Its unique
`http-evidence-20261018T233934786954Z-0173e1f6.json` contains 918 exchanges targeting
`https://cra-phase3-api-456725640364.us-central1.run.app/api/v1`. Both the user and
runner identify deployed SHA `7686edf`; that remains operator-supplied provenance,
not an independently inspected Cloud Run revision/image digest.

For `test_clock_aware_input_uses_utc_date[2026-11-01T23:59:59.123456+02:00]`:

| UTC interval, October 18, 2026 | Request / outcome |
|---|---|
| 23:41:43.170934–43.428551 | Runner's setup reset completes, 204 |
| 23:41:43.493227–43.692342 | Fractional offset clock accepted, 200; normalized to `2026-11-01T21:59:59.123456Z` |
| 23:41:43.692342–44.415286 | POST release returns undocumented 404 `NOT_FOUND`, `Release not found`; request ID `031331cc17d54da0a41b9d20886bf735` |
| 23:41:44.616793–44.940943 | Next test's setup reset, after the failed request finishes |

The timestamp parser succeeded. This runner records no overlapping reset in the
failed POST interval. Its trace cannot see a different client, test run or direct
database action. The deployed code's release INSERT commits, closes its connection,
then calls `get_release()` in a new transaction. An intervening reset can remove
the row, producing exactly the observed error. Reset is the only application path
that deletes releases; schema startup does not clear them. This is a **confirmed
application defect and a plausible explanation for the hosted failure**, not proof
that a concurrent reset actually occurred on Google Cloud.

To check that hypothesis, inspect existing Cloud Run logs for service
`cra-phase3-api` around `2026-10-18T23:41:42Z`–`23:41:46Z`, including every revision:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="cra-phase3-api"
timestamp>="2026-10-18T23:41:42Z"
timestamp<="2026-10-18T23:41:46Z"
```

Locate the failed request ID and any `/api/v1/test/reset` request overlapping its
server execution, using platform request latency and application duration logs.
If absent, investigate direct SQL cleanup, revision/image provenance and database
connection configuration. No cloud logs or database contents were inspected here.

### Fix and regression strategy

Creation now uses `INSERT ... RETURNING` and reads the UTC reference clock using
the same cursor/transaction. It constructs the normal release response before
commit, then returns it only after successful commit. There is no post-commit
release lookup or clock connection. GET reuses the response formatter; public
fields, routes, 201/400/409 behavior, UTC end-of-day semantics and reset's 204
semantics are unchanged. Clock-query failures roll back the insertion rather
than leaving a row behind after a failed creation response.

PostgreSQL's INSERT table lock conflicts with reset's TRUNCATE lock until the
transaction completes. After commit, reset may still remove the release; a later
GET legitimately returns 404. The response describes the completed creation.
See [INSERT RETURNING](https://www.postgresql.org/docs/16/sql-insert.html) and
[table-lock compatibility](https://www.postgresql.org/docs/16/explicit-locking.html).
No locks spanning HTTP requests, new authentication, test namespaces, delays,
retries hiding the failure, or shared-contract changes were added.

- Six unit regressions cover reset immediately after commit, the exact fractional
  offset input, UTC date rollover in either direction, system-clock fallback,
  rollback after a clock-query failure and refusal to report success on commit
  failure. Before the fix: **5 failed / 1 passed**; after: **6 passed**.
- `scripts/check_release_reset_race.py` instruments a separate loopback-only
  Uvicorn process inside the new test API container. Events pause POST immediately
  after its real PostgreSQL commit, allow a second HTTP request to reset state
  and change the clock, then resume POST. There are no production test hooks or
  timing-dependent random stress loops. Before the fix it reproduced the exact
  HTTP 404 envelope; afterward **both supported/unsupported cases return 201**
  with their captured clock status, and subsequent GETs correctly return 404.
- CI now runs that deterministic Docker regression, guarded by explicit
  `CRA_RACE_TEST_ALLOW_RESET=1` plus test-only database/host checks. It is not a
  portable test for Cloud SQL or another team's deployment.

### Final local results and preservation

New isolated project: `cra-phase3-deployment-release-race-20261018`, port **18085**,
new `cra_test` PostgreSQL and `cra-phase3-deployment-release-race-20261018_pgdata_test`
volume. **297 tests passed / 0 failed / 0 skipped**, 28.07 seconds: 157 Docker HTTP
acceptance/regression tests and 140 local tests, including the six new regressions.
The formerly failing fractional-offset HTTP case passes locally. Both controlled
HTTP reset interleavings and the separate forced SBOM SQL-rollback check pass;
the latter retains 25 prior components with no idle transactions. Ruff lint and
format checks pass for 17 Python files; mypy passes both service modules; shared
OpenAPI/25 locked fixture packages/17-operation validation passes. Only the existing
dateutil deprecation warning remains. This is not a successful hosted rerun.

Ignored evidence is under `artifacts/release-reset-race/`: `unit-before.xml`,
`unit-after.xml`, `http-race-before.log`, `http-race-after.log`, `sbom-rollback.log`,
preservation/protected-input snapshots, and `final/` containing JUnit,
`http-evidence-20261018T235101323353Z-89b9c387.json` (918 exchanges), operation
observations/status, image/source provenance and service logs. Source hashes and
the dirty checkout distinguish this local image from committed deployed `7686edf`.

The original 16 container identities/images/mounts/ports/running states and five
volumes are preserved. Original live database rows/hashes remain **1 release /
0 components / 0 clock rows**. Shared OpenAPI, fixtures, both Compose files and
all three supplied cloud evidence files are unchanged. New synthetic data is
confined to the new test project, stopped with its volume retained after testing.

Remaining work: review this fix; inspect cloud logs to establish the historical
trigger; obtain commit/push/redeployment authorization; then rerun all 157 portable
HTTP tests on the approved deployed image during a coordinated exclusive reset
window. Global reset/clock controls still let separate suites interfere across
multiple requests; the creation fix does not provide suite-wide isolation.

## October 26 — independent HTTP autograder system and tester

Starting checkout: clean `main`, `609ab4038b7c8cf3de060470fcd628e81fa15c0a`.
This increment is local and uncommitted; no push, GitHub Actions run or cloud
deployment occurred. The prior release/reset fix is committed. Existing saved
`artifacts/google-cloud-rerun` evidence records 157/157 against operator-supplied
target SHA `609ab40`; that does not establish a deployed adapter revision.

Only Team 6's README/OpenAPI documentation was read, pinned at
`9c0b1917b6ed316d51b412685805bd8766b8edea`. It is a provisional external-interface
reference, not official staff approval. No peer implementation/test files were
read or copied. Our original shared contract, fixtures, `test_api.py` and
`conftest.py` remain unchanged. Both roles run the original assertions.

### Actual local results

| Verification | Result / evidence |
|---|---|
| Before edits: existing non-HTTP regression suite | 140 passed |
| Original HTTP collection, before and after | 157 cases, unchanged |
| Full final original + new local suites | **345 passed, 0 failed, 0 errors, 0 skipped**, 25.72 s; `artifacts/autograder/regression-final-results.xml` |
| Breakdown of 345 | Original 297 (157 HTTP + 140 local), 5 new system adapter tests, 43 tester unit/health/store tests |
| Full actual HTTP adapter suite | **7 passed**, 83.90 s; `artifacts/autograder/http-final-results.xml` |
| System setup → run → report | 157 passed / 0 failed/errors; real subprocess 24.583 s; `system-report.json` |
| Tester setup → run → report | 157 passed / 0 failed/errors; real subprocess 24.940 s; `tester-report.json` |
| Intentionally broken local HTTP target | **157 actual assertion failures**, 0 errors, accurately returned `result: fail`; 5.502 s; `failing-report.json` |
| Runtime restart/kill/timeout checks | 3 passed; `artifacts/autograder/runtime-results.json` |
| Schema startup compatibility | All 6 existing real PostgreSQL checks passed, including 6 concurrent initializers and legacy row preservation |
| Release creation/reset race | Both existing controlled HTTP/SQL interleavings passed: creation 201 with captured support status; subsequent GET 404 after intentional reset |
| SBOM rollback | Injected final nested INSERT failed cleanly; 25 prior components retained; JSON 500; no idle transactions |
| Ruff lint / format | Passed, 30 Python files formatted |
| mypy | Passed, 8 production source files |
| Shared contract/fixture check | OpenAPI 3.1 valid; all 25 locked packages match; 17 original operations reported |
| Separate extension schema | OpenAPI 3.1 validation passed; CI's inline validation command also executed locally |
| Both final Docker builds | Passed, Python 3.11 slim; existing and new Compose configurations validated |
| JSON homepages and tester DB readiness | Real HTTP 200 on both `/` routes and tester `/health/ready` |
| GitHub CI / public adapters | **Not run / not deployed** for this increment |

These counts describe outer pytest cases; the 157-case child runs inside the
seven HTTP checks are additional executions, not extra collected outer cases.
Final local pytest emits one existing dateutil Python 3.12 deprecation warning.
The containers execute Python 3.11, as CI is configured to do.

The seven HTTP checks validate responses against both our extension schemas and
the four corresponding operations from the pinned Team 6 OpenAPI, supplied via
`TEAM6_AUTOGRADER_SPEC=artifacts/autograder/team6-reference.yaml`. Extra setup
409/configuration 503 responses are documented Team 2 safety policies; this does
not prove staff protocol approval, timing compatibility or live peer conformance.
Real checks include malformed input, unknown sessions, unapproved/null targets,
query/JSON sessions, immutable completed retries, invalid clock without reset,
timezone-aware system setup, required per-test fields and overlapping adapter
setup/run rejection. Completed reports survive tester restart. A killed active
run is recovered as error; prior reports remain intact. A second tester instance
shares reports; a real one-second run timeout kills its child and persists error.

During development, a new concurrency test first failed because report reads
briefly acquired the execution mutex. Ordinary ready/completed polling no longer
acquires it; a dedicated store regression and full HTTP reruns pass. A combined
Windows run initially produced 328 passed / 17 **setup errors** because the
escalated identity could not use an existing host pytest temp directory. Its XML
is retained as `regression-results.xml`. The final run used a fresh workspace
`--basetemp artifacts/autograder/tmp-<unique-id>` and all 345 passed. Earlier
format/type checks exposed issues that were corrected before the final checks;
the final results above do not hide those intermediate failures.

### Isolation, data preservation and reproducibility

Docker Desktop was initially stopped; it was started locally for these checks.
Its existing restart-policy containers resumed automatically. No existing
container was rebuilt/reconfigured and no database/volume was deleted. Destructive
calls were confined to the newly created project
`cra-phase3-autograder-20261026`, ports 18086/18087, its own
`cra-phase3-autograder-20261026_harness_test` volume and intentionally broken
container target. A separate timeout-only tester container was created, tested
and stopped, with its shared test volume retained. No cloud or Team 6 reset/run
request was made. The three startup-check synthetic databases are also retained
inside the new test project's PostgreSQL instance.

After verification the new test stack was stopped with `docker compose stop`;
its containers, reports and volume are retained. The original running services
were not stopped. Start the dedicated project again to inspect its local reports.

Read-only before/after snapshots of the original `cra_postgres` database match:
1 release, 0 components, 0 clock rows. Row-content hashes are unchanged:
`08eb20aebbbbe38d1da4907ae9f03721` for releases and
`d751713988987e9331980363e24189ce` for each empty table. All six pre-existing
Docker volumes remain, including `cra-service_pgdata`. Original CRA schema and
stored data remain untouched. Existing Compose build definitions changed only
to select the root context/Dockerfile; ports, passwords, DB settings, service
names and named volumes did not change.

Run commands and the metadata lock's cooperation/network-partition limits are in
`autograder-interface.md`. Deployment and registry steps are in
`deployment-tester-google-cloud.md`. A separate disposable grading database and
shared persistent report database on the existing Cloud SQL instance must be
configured and verified before enabling cloud resets. This does not authorize
cloud changes or establish Cloud SQL report connectivity.

### Files in this increment

New runtime: `cra-service/autograder/__init__.py`, `api.py`, `config.py`,
`runner.py`, `store.py`, and `cra-service/requirements-harness.txt`.
New separate tester: `tester-service/app.py`, `Dockerfile`, `requirements.txt`,
`.env.example`, `docker-compose.test.yml`.
New tests/helpers: `cra-service/test_autograder.py`,
`tester-service/tests/test_core.py`, `test_store.py`, `test_tester_health.py`,
`test_http.py`, `broken_target.py`, and `scripts/check_autograder_runtime.py`.
New build/docs: root `.dockerignore`, `cloudbuild-tester.yaml`,
`docs/autograder-openapi.yaml`, `autograder-interface.md`,
`deployment-tester-google-cloud.md`.
Modified: `cra-service/main.py`, `Dockerfile`, both existing Compose build
definitions, `cloudbuild.yaml`, `.github/workflows/ci.yml`, `pyproject.toml`,
`README.md`, and `docs/decisions.md`, `project_context.md`, `phase3_status.md`,
`models.md`, `deployment-google-cloud.md`, `testing.md`.
No existing files were deleted or moved. Generated evidence remains ignored.

## October 26 — final autograder safety corrections

The final review identified two safety defects: Requests could forward a reset
POST through a 307/308 redirect outside the selected target, and system settings
could default to our public service while verifying a different local database.
The deployment guide also created built-in Cloud SQL users without preventing
automatic administrative roles and omitted the grading schema CREATE grant.

Implemented corrections:

- New `cra-service/autograder/pytest_guard.py` is loaded explicitly by the harness
  child with `-p`; original `test_api.py` and `conftest.py` are unchanged. Every
  prepared HTTP request must match the selected origin and `/api/v1/` path;
  all redirects are disabled and inherited proxies bypassed. Newly created
  sessions and the concurrent SBOM test are covered. Runner reauthorizes the
  target immediately before starting a child.
- System settings default only to `http://127.0.0.1:PORT`; remote/wrong-port
  overrides are rejected even if allowlisted. Adapter setup/run require both
  configured and connected DB names to be `cra_grading`; retained/course DB names
  are not alternative reset approvals. Original CRA API handlers are unchanged.
- System discovery adds optional `reset_ready`, using a read-only config/database
  check. Before testing our known public URL, the tester requires role system and
  this signal true; old/unready course revisions are refused before pytest starts.
  Team 6 is not required to implement this Team 2-only safety signal. The separate
  extension schema documents it; our shared OpenAPI is untouched.
- The Console guide now specifies ordinary SQL login roles, separate grading and
  metadata database grants, public-schema usage/create only for the grading role,
  password prompts/Secret Manager, and permission verification. New candidate
  revisions start with controls disabled; verify the DBs/roles, switch 100% system
  traffic to grading, confirm discovery readiness, then enable the tester.

Actual final results (all fresh local data):

| Check | Result |
|---|---|
| Non-destructive tests included in full run | **232 passed** (140 original local, 9 adapter, 83 tester unit/health/store/safety) |
| Full regression + unit run | **389 passed / 0 failed / 0 errors / 0 skipped**, 25.14 s |
| Original HTTP case collection | **157 unchanged cases** |
| Actual system/tester adapter HTTP suite | **8 passed**, 86.56 s; responses validated against our extension and pinned Team 6 schemas |
| System child suite | **157 passed**, 23.081 s |
| Tester child suite | **157 passed**, 23.728 s |
| Intentionally broken HTTP target | **157 real assertion failures**, correctly reported fail |
| Redirect target to an unapproved sentinel | **157 fixture errors**, correctly reported error; **0 destructive requests reached the sentinel** |
| Storage/runtime checks | **6 passed**: ordinary roles/cross-DB permissions, report survives domain reset, report survives tester restart, killed run recovery, timeout child cleanup/shared report, wrong DB approval refused without deleting a grading release |
| Ruff / format | Passed; 33 Python files formatted |
| mypy | Passed; 9 production source files |
| Both OpenAPI documents | Valid OpenAPI 3.1 |
| Final Docker builds | Passed; guard plugin and both services ran in Python 3.11 images |
| GitHub CI / cloud | Not run / not deployed for this uncommitted increment |

The 40 new transport/public-target unit cases include 301/302/303/307/308 redirects
for POST/PUT to same/different origins, new sessions, direct unapproved requests,
proxy bypass, missing plugin target, default/alternate PORT, remote/wrong-port
overrides, pre-spawn authorization and old/unready public revisions. Four more
adapter cases cover retained database approval. An initial mypy missing-stubs
finding was resolved with scoped `import-untyped` annotations; final lint/type
checks and tests pass. Pytest still emits one existing dateutil deprecation
warning on the host Python 3.12. The containers use Python 3.11.

Evidence is retained, ignored by Git, in `artifacts/autograder-safety/`:
`regression-final-results.xml`, `http-final-results.xml`, `runtime-results.json`,
system/tester/failing/redirect report JSON, sentinel results, HTTP evidence and
preservation snapshots. Earlier first-pass 381/8 results are separate from the
final 389/8 run after adding public-target readiness protection.

All reset-based tests ran only in the new
`cra-phase3-autograder-safety-20261026-01` project, host ports 18089/18090 and a
new dedicated volume, verified absent before creation. Its init SQL creates
separate `cra_grading` and `cra_autograder` databases and ordinary runtime roles;
it is test-only and is never used against Cloud SQL. The SQL role checks prove
no SUPERUSER/CREATEDB/CREATEROLE/REPLICATION, correct schema access, and no CONNECT
between the two runtime databases. Temporary timeout/unsafe-config containers
belong only to this new project and were stopped with their storage retained.
The six main test services were then stopped, without deleting the volume.

Before/after read-only Docker inventories confirm **all 23 pre-existing container
identities/images/mounts/running states and all 7 pre-existing volumes unchanged**.
No SQL or reset requests were issued to any pre-existing database, public service
or Team 6 system. Shared OpenAPI, fixtures and the original HTTP test/fixture files
remain unchanged. No commit, push, cloud change or deployment occurred.

Additional files in this safety increment: `autograder/pytest_guard.py`,
`tester-service/tests/test_transport_safety.py`, `init-databases.sql` and
`transport_target.py`. Updated pending files include config/runner/adapter code,
adapter/core/HTTP tests, the isolated harness Compose file/runtime checker, and
the extension/deployment/context/status/decision/testing/README documents.

No local implementation blocker remains from the three findings. Before hosted
use, obtain deployment approval, provision and verify the documented Cloud SQL
roles/secrets, switch the system to its disposable grading DB, validate deployed
readiness and run acceptance in an exclusive window. GitHub Actions must run
after an approved push. Direct legacy resets and independent peer testers still
require coordination; the cooperative mutex does not fence those clients.
