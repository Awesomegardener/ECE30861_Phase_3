# ECE 30861 CRA Phase 4 service

FastAPI + PostgreSQL + Docker service for release registration, CycloneDX SBOM
inventory, CVE impact analysis and incident/deadline management. The Phase 4
implementation is merged into `main`, passed GitHub Actions and is deployed on
Google Cloud Run with Cloud SQL PostgreSQL. This is a course-project increment;
the complete CRA implementation and production vulnerability-feed operations are
not finished.

## Current deployment and verified results

The deployment details and public test results below are verified information
supplied by Team 2. They were not rerun during this README-only update.

| Deployment field | Current value |
|---|---|
| Google Cloud project | `cra-vulnerability-service` |
| Region | `us-central1` |
| System | [cra-phase3-api](https://cra-phase3-api-456725640364.us-central1.run.app) |
| Tester | [cra-phase3-tester](https://cra-phase3-tester-456725640364.us-central1.run.app) |
| Deployed source commit | [`9e1dae298eaa4e09fd94d0e86366d37ba37f6806`](https://github.com/Awesomegardener/ECE30861_Phase_3/commit/9e1dae298eaa4e09fd94d0e86366d37ba37f6806) |
| System revision | `cra-phase3-api-00006-jop` |
| Tester revision | `cra-phase3-tester-00002-hak` |
| Repository status | `main` contains the Phase 4 implementation |

The automated portable HTTP suite contains **353 cases**: all **157 original
Phase 3 cases** plus **196 Phase 4 cases**.

| Verified testing direction | Passed / total |
|---|---:|
| Team 2 tester against Team 2 system | **353 / 353** |
| Team 2 tester against Team 6 system | **341 / 353** |
| Team 6 tester against Team 2 system | **48 / 50 required checks** |

Cross-team differences remain unresolved; these totals do not identify the causes
or establish complete compatibility. Per-check reports and agreed resolutions
are still needed. Passing checks are not a source-code coverage measurement.
See the [cross-team run guide](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/phase4-cross-team-testing.md)
and [Q6.1 evidence template](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/phase4-q61-results-template.md).

## Phase 4 capabilities and documentation

- **CVE impact analysis (REQ-03):** queries stored component inventories and groups
  affected releases by current UTC support status. Versioned PURL matching ignores
  qualifiers/subpaths; components without PURLs cannot match affected PURL entries.
- **Vulnerability-source handling (REQ-04):** distinguishes unknown CVEs, known but
  unaffected inventory and source unavailability. Supports a separate deterministic
  grading source and validated local OSV snapshots with provenance and freshness
  checks; grading fixtures are not production vulnerability-feed integration.
- **Incident registration (REQ-05):** persists awareness time, mandatory/voluntary
  classification, rationale and actor attribution, with format-checked optional
  CVE IDs and updates to fix availability.
- **Reporting deadlines (REQ-06):** computes mandatory early warning at awareness
  +24 hours, notification at +72 hours and final report at fix availability +14
  days. UTC statuses are calculated on read; voluntary stages remain not_applicable.
  This tracks deadlines and submissions, not regulatory report generation or push alerts.

Current implementation and operating references on `main`:

- [Phase 4 implementation and API semantics](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/phase4-implementation.md)
- [Architecture and data models](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/models.md)
- [Phase 4 paired deployment and rollback guide](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/deployment-phase4.md)
- [Google Cloud Console guide](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/deployment-google-cloud.md)
- [Separate tester deployment guide](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/deployment-tester-google-cloud.md)
- [OSV snapshot operations and limits](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/osv-snapshots.md)
- [OSV architectural decision](https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/adr-0001-osv-snapshots.md)

Some linked reviews, evidence drafts and deployment guides retain pre-deployment
status statements. Those statements are historical snapshots; the deployment
and public results above supersede them. Their technical procedures and stated
limitations still need to be considered.

The authoritative pod interface remains [`docs/openapi.yaml`](docs/openapi.yaml).
It and the shared [`fixtures/`](fixtures/) have not been changed by this update.
[`docs/openapi.phase4-proposed.yaml`](docs/openapi.phase4-proposed.yaml) is separate
and remains pending Team 6's final review; deployed behavior does not constitute
approval of a shared-contract change.

New API examples, after selecting an authorized disposable target and setting
`VULNERABILITY_SOURCE=fixture`, `VULNERABILITY_TEST_MODE=true`, and
`VULNERABILITY_TEST_DATABASE=cra_grading` on the system:

```http
PUT /api/v1/test/vulnerability-source
Content-Type: application/json

{"mode":"available","records":[{"cve_id":"CVE-2026-12345","affected_purls":["pkg:generic/example@1"]}]}

GET /api/v1/vulnerabilities/CVE-2026-12345/affected-releases

POST /api/v1/incidents
Content-Type: application/json
X-User-Id: engineer-17

{"awareness_at":"2026-11-01T00:00:00Z","classification":"mandatory","rationale":"Confirmed exploitation","cve_id":"CVE-2026-12345"}

PATCH /api/v1/incidents/RETURNED_INCIDENT_ID
Content-Type: application/json
X-User-Id: engineer-17

{"fix_available_at":"2026-11-03T00:00:00Z"}

POST /api/v1/incidents/RETURNED_INCIDENT_ID/submissions
Content-Type: application/json
X-User-Id: engineer-17

{"stage":"early_warning","submitted_at":"2026-11-02T00:00:00Z"}

GET /api/v1/incidents/RETURNED_INCIDENT_ID
```

The original retained `cra_phase3` DB must never be used for this revision;
startup refuses it before DDL. Local development uses the existing Compose setup
with its original DB/volume; run destructive tests only in a separate fresh stack.

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

Application: `http://localhost:8080` (JSON homepage); generated docs: `/docs`. PostgreSQL uses
the existing `pgdata` named volume and is bound to loopback. Schema initialization
serializes concurrent starts and widens existing string columns only when needed,
without deleting records. Normal API/DB restarts
retain data. Do not delete the database volume to upgrade the application.

Operational health: `/health/live` returns 200 without querying PostgreSQL;
`/health/ready` returns 200 after a short read-only query, or generic 503 when
the database is unavailable. Both omit shared API schemas. Docker uses `PORT`
when provided and defaults to 8080; the existing Compose mappings stay unchanged.

## HTTP system and tester adapters

Both system and separate `tester-service/` expose discovery, setup, synchronous
run and report at `/test*`. They now run both portable pytest files (353 cases) and
persist real per-test outcomes in PostgreSQL, with a shared execution lock.
Controls default disabled and require explicit disposable-target authorization.
System self-tests are restricted to loopback at `PORT`, and adapter resets to
the dedicated `cra_grading` database. Harness subprocesses block redirects and
unapproved destinations. Our public target must advertise guarded reset readiness
before the tester launches destructive checks. The local harness stack uses
separate grading/report databases and ordinary roles in a new isolated volume.
The separate system and tester URLs and current revisions are listed above.
The GitHub Python source-file URL is not a deployed tester URL.

- [Protocol, safety boundaries and local HTTP verification](docs/autograder-interface.md)
- [Separate provisional HTTP contract](docs/autograder-openapi.yaml)
- [Console deployment, settings, secrets and registry](docs/deployment-tester-google-cloud.md)

Both Dockerfiles now build from the repository root, for example
`docker build -f cra-service/Dockerfile .`; existing Compose commands still work.
CRA database settings, ports and persistent volume names are preserved. The
extension does not replace our shared specification. Phase 5 remains deferred.

## Run tests without clearing application data

The HTTP suite calls `/api/v1/test/reset`. Use the dedicated test stack, which has a
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

## Save HTTP test evidence

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
.\.venv\Scripts\python.exe -m ruff check cra-service tester-service scripts
.\.venv\Scripts\python.exe -m ruff format --check cra-service tester-service scripts
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -X utf8 -B scripts/check_contract.py
```

[GitHub Actions run 41357984819](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/41357984819)
passed for the deployed Phase 4 source commit `9e1dae2`. The system/API job passed
**701 tests**, and the autograder job passed **97 regressions and 8 HTTP integration
checks**, including saved reports with **353 passing cases from each adapter**.
Startup, rollback, source handling, persistence, locking and timeout checks also
passed. These are isolated CI results, separate from the public results above.
CI uploads synthetic results/logs and records its checkout SHA. Repository branch
protection determines whether checks block merges; no current protection setting
is assumed here.

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

## Known limitations and remaining work

- **Production OSV feed operations are incomplete (REQ-03/04).** Real snapshot
  fetching, schema validation, atomic PostgreSQL ingestion, provenance and local
  matching are implemented. Production coverage selection, automated refresh,
  freshness monitoring, retention and representative full-feed performance still
  need operational verification. Explicit versions, SEMVER and PyPI ECOSYSTEM
  ranges are supported; other native ecosystem and Git-range comparisons remain
  unsupported and return source-unavailable when needed. A passing fixture-backed
  test run does not prove complete production OSV integration.
- **Report generation (REQ-07) is deferred.** HTTP tester reports are execution
  evidence, not generated regulatory reports or submissions to authorities.
- **Immutable audit logging (REQ-08) is incomplete.** Persisted incident/submission
  attribution and latest update metadata do not provide a complete append-only
  history of corrections or satisfy the full Phase 5 audit scope.
- **Cross-team differences remain.** The reported 341/353 and 48/50 required-check
  results need per-case diagnosis and coordinated resolution. Proposed contract
  additions and fixture review/sign-off remain separate from deployment success;
  do not infer final Team 6 approval from these results.
- **Reset-based testing requires coordination.** Use disposable grading data and
  explicitly approved targets, run one suite at a time and reconfirm Team 6's
  current URL and reset authorization before another run. Never target retained
  `cra_phase3` or a production OSV inventory. Deadline statuses are calculated on
  retrieval; no Phase 4 push-alert service is implemented.

OSV records, provenance and the active snapshot pointer persist in PostgreSQL;
Cloud Run's temporary filesystem is not the durable source. Missing/stale snapshots
and unavailable storage fail explicitly. Database readiness alone does not certify
snapshot freshness. See [OSV operations](docs/osv-snapshots.md).

## Historical Phase 3 evidence

The following records are retained for traceability and do not describe current
Phase 4 deployment readiness:

- [Baseline CI run for `f27cfd5`](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39157992256)
  passed. The earlier deployment-readiness increment reported 291 local tests,
  including 157 original HTTP cases.
- The earlier deployed `7686edf` run recorded 156 passed and 1 failed. The
  release/reset race fix at `609ab4038b7c8cf3de060470fcd628e81fa15c0a` subsequently
  recorded 157 passed and 0 failed. See [the investigation and regression evidence](docs/testing.md#release-creation--concurrent-reset-investigation).
- Earlier records for `ad42a43`, the [pre-deployment Phase 4 review](docs/phase4-pod-update.md)
  and [evidence draft](docs/phase4-evidence-draft.md) describe the state before the
  current merged/deployed source commit and are retained as historical records.

Cloud builds and deployments remain distinct operations. Root `cloudbuild.yaml`
and `cloudbuild-tester.yaml` build/publish images; they do not deploy or switch
traffic. Further deployments, cloud configuration changes and database operations
require explicit authorization and coordinated testing.
