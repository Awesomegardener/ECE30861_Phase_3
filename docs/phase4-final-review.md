> Historical review/proposal, superseded November 1, 2026 by [the pod update](phase4-pod-update.md) and [OSV ADR](adr-0001-osv-snapshots.md). Counts and source limitations below describe the earlier implementation, not the current code.

# Phase 4 final review — November 1, 2026

Base: `main`, `ad42a439b81fdfd42ab50e44cea4c53717d07769`, plus local changes.
No commit, push, merge, cloud command or deployed-system test was performed.

**Verdict:** reviewed code is suitable to commit after user approval. A coordinated,
explicitly fixture-only grading rollout is technically prepared, subject to CI,
secrets/DB/traffic verification and reset authorization. Do **not** describe or
promote it as complete Phase 4 production vulnerability integration: Dependency-
Track and the agreed pod Phase 4 manifest remain missing. Resolve that decision
before claiming full production delivery. This review cannot establish current
cloud configuration, CI success for uncommitted code or Team 6 agreement.

## Findings, fixes and unresolved issues

| Priority | Finding | Resolution/status |
|---|---|---|
| High, open delivery gap | Only seeded fixture matching exists; Phase 2 selected Dependency-Track. | Concrete infrastructure/authentication/sync/cost/test plan in `dependency-track-integration-plan.md`. Complete it or document an appropriately approved plan change before a full production claim. |
| High validation defect, fixed | JUnit parser accepted 311 passing records even if all were duplicates or all came from the original file. | Reproduced both false passes with two failing regressions, then fixed. Require unique identities, 157/154 required-file counts and new AC counts 6/10/55/83; actual outcome counts remain truthful. |
| Safety default, fixed; deployed configuration still requires review | Tester implicitly allowed Team 6 even with no explicit peer allowlist. | Default now approves only Team 2. Explicit local test origins still work. Added regression; `.env.example`/guides use Team 2 only. Existing cloud environment overrides are unchanged and must be checked before deployment. |
| High operational risk, guide corrected | A 0%-traffic tag shares live `cra_grading`; its setup/run resets could erase data used by the live revision. | Pre-switch checks are read-only; destructive acceptance requires separate explicit grading-reset permission and an exclusive window, or a genuinely isolated environment. Traffic rollback cannot restore cleared data. |
| Test-oracle weakness, fixed | CVE tests checked PURLs but could miss wrong CVE/component names/versions or duplicates. | Added exact CVE/tuple/count assertions to existing five-CVE tests. Added UTC awareness read-back and unchanged-state checks after invalid mutations. Original assertions retained. |
| Runtime-check repeatability, fixed | Submission SQL check counted rows from all prior evidence runs. | Query now uses a SQL parameter for this run's incident and verifies its four attributed submissions. Five runtime checks passed twice without resetting between repetitions. |
| Git hygiene, fixed | `.gitignore` covered `.env` but missed common environment/key/DB/log variants. | Added patterns and verified sample secret/artifact paths are ignored while `.env.example` is allowed. No real secrets added. |

No additional critical deadline-math, transaction/rollback or Phase 3 regression
defect was found in the reviewed code and local tests. Public controls remain
unauthenticated by the course interface design: `X-User-Id` is attribution, not
authorization. Only disposable grading deployments should expose reset/fault
injection; this is not a secure general-purpose production incident service.

## Requirement and acceptance review

| Requirement | Implementation / evidence | Completion |
|---|---|---|
| REQ-03 / AC-04 | Exact PURL matching against stored flattened inventory; each release once, matched occurrences preserved; UTC current/boundary support grouping. Five synthetic CVEs check full fields, precision/recall and <10-second latency. | Deterministic behavior verified; production source and pod ground truth incomplete. |
| REQ-04 / AC-05 | Known-unaffected 200 empty arrays; unknown 404 CVE_UNKNOWN; outage/unconfigured source 503 VULNERABILITY_SOURCE_UNREACHABLE; invalid configuration atomic. | Fixture behavior verified; real Dependency-Track outage/auth/mirror behavior not implemented. |
| REQ-05 / AC-06 | PostgreSQL awareness/classification/rationale/creator, strict aware times normalized to UTC, required header, mandatory/voluntary cases and error paths. | Implemented and locally verified; hosted/cross-team and human rationale review pending. |
| REQ-06 / AC-07 | Independent awareness+24h/+72h and fix+14d deadlines, dynamic pending/met/overdue, exact boundaries, late submissions, offsets, leap/year/month rollover, invalid inputs, restart persistence. | Implemented and locally verified; hosted/cross-team verification pending. |

The 157 original cases and `conftest.py` are unchanged in Git. All 154 Phase 4
cases run through HTTP and assert observed behavior; 87 parameterized cases
cover the shared invalid-time set across three incident timestamp fields.
Breakdown: AC-04 6, AC-05 10, AC-06 55, AC-07 83. Five new review regressions are
local adapter tests, **not** extra hosted cases; the HTTP total remains 311.

`docs/openapi.yaml` and all Team 6 fixtures are unchanged. Affected-release
200/404/503, incident create 201/400, incident get 200/404, patch 200/400/404 and
submission 201/400/404 response bodies are checked against shared schemas.
Headers/test-control exemptions and exact agreed CVE error codes are preserved.
The complete 17-operation status is emitted under ignored evidence; 12 routes
are present, five report/audit operations remain intentionally Phase 5.

Do not claim unconditional contract completeness: shared YAML omits negative
responses for test controls and invalid-CVE input, and infrastructure failures
can return the existing sanitized 500. Clock/source invalid 400, source-disabled
503 and invalid-CVE 400 are disclosed extensions/omissions. Nonblank rationale
is stricter than the YAML's bare minLength:1, following the meaningful-rationale
interpretation. Duplicate submissions use earliest time; omitted source records
preserve prior data; final filings before a fix and fix correction remain local
choices needing pod confirmation. The null/not_applicable final deadline before
a fix follows the Phase 2 example. No shared policy approval was invented.

## Database and deployment safety review

The existing transaction startup lock serializes additive creation of incidents,
submissions, source state and indexes in `cra_grading`. Hash equality indexing
does not introduce a B-tree size limit on valid long PURLs. Existing release and
SBOM rows are not rewritten/deleted by this increment's migration. Legacy
initialization tests preserve original rows/timestamps; concurrent initializers,
rollback and repeated startup are verified. Runtime checks preserve new incident,
submission/source state across API restart. Startup refuses retained `cra_phase3`
before any DDL; no migration was applied to any existing database during review.

`deployment-phase4.md` now separates routing from storage isolation. Build both
images at the same reviewed SHA/digests, deploy system candidate with 0% traffic,
read-only health/schema/discovery checks, then a coordinated system-first/tester-
second rollout. Existing service names retain both public URLs. Use fresh setup
IDs and require 311 checks and the correct runner SHA; cached historical reports
remain available but are not new acceptance evidence. Keep startup probes and
900-second request/600-second child budgets; actual child runs were about 50 s.

For fixture-only rollout, no new runtime secret, IAM grant, cloud service or paid
database instance is required beyond the existing verified Cloud SQL/Secret
Manager configuration. Existing costs continue. Actual Dependency-Track adds
infrastructure/secrets/network/worker permissions/costs described separately.

If candidate startup/DB checks fail, leave old traffic unchanged and inspect
sanitized logs/configuration. Transactional migration failure rolls back. If tests
fail, stop them before reverting both revision allocations; keep additive tables
and compatible secrets. Code rollback does not restore grading rows removed by
an explicitly approved reset. No reset/snapshot restore of `cra_phase3` is allowed.

## Final local verification and exact commands

All final tests passed. One pre-existing dateutil deprecation warning appears on
host Python 3.12; Docker uses Python 3.11. The two initially failing parser tests
are intentional defect reproduction, not unresolved failures.

| Check | Actual result |
|---|---|
| Non-destructive tests | 378 passed |
| Complete pytest suite | **689 passed**, 0 failed/errors/skipped, 54.12 seconds |
| Real HTTP adapter checks | **8 passed**, 165.32 seconds |
| System child | **311/311**, 0 failed/errors/skipped, 50.327 seconds |
| Tester child | **311/311**, 0 failed/errors/skipped, 47.963 seconds |
| Per-check HTTP evidence | All 311 checks on each role have request/response examples |
| Phase 4 runtime checks | 5 passed, then all 5 passed again without a reset |
| Existing adapter storage/safety checks | 6 passed |
| Concurrent schema/startup/preservation checks | 6 passed |
| Deterministic release/reset race | 2 passed |
| Real SBOM rollback | Passed; 25 old components retained, sanitized 500, no idle transactions |
| PORT/health/retry/restart/graceful shutdown | Passed |
| Ruff lint/format, mypy | Passed; 38 Python files formatted, 11 production files type checked |
| Shared and adapter OpenAPI 3.1, 25-package fixture | Passed; 17 shared operations reported |

Only newly created projects were used:
`cra-phase3-autograder-phase4-final-20261101-01` (18206/18207, separate grading/
report DBs) and `cra-phase3-deployment-phase4-final-20261101` (18226, cra_test).
No previous test volume was reused. Evidence under `artifacts/phase4-final-review/`
is ignored: `full.xml`, `adapters.xml`, per-role reports, HTTP bodies/UTC times,
runtime JSON, source hashes and startup/race/rollback logs. Source is the base
SHA plus dirty files; no target deployment SHA was fabricated. Local lookup max
was 0.032 seconds over 23 responses, not a hosted/large-load performance claim.

Commands actually run from repository root (PowerShell, each phase sequential;
the two DB projects are independent). Stop after any nonzero exit:

```powershell
$python = '.\.venv\Scripts\python.exe'
$docker = 'C:/Users/Lenovo-User/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe'
$harness = 'cra-phase3-autograder-phase4-final-20261101-01'
$deployment = 'cra-phase3-deployment-phase4-final-20261101'
$env:HARNESS_SYSTEM_PORT = '18206'
$env:HARNESS_TESTER_PORT = '18207'
$env:HARNESS_SENTINEL_PORT = '18212'
# Each project/volume was checked absent before the following commands.
& $docker compose -p $harness -f tester-service/docker-compose.test.yml up --build -d --wait --wait-timeout 240
& $python -X utf8 -B -m pytest cra-service tester-service/tests --ignore=tester-service/tests/test_http.py --allow-reset --base-url http://127.0.0.1:18206 --capture-http-bodies --evidence-dir artifacts/phase4-final-review/full --junitxml artifacts/phase4-final-review/full.xml --basetemp artifacts/phase4-final-review/full-tmp -p no:cacheprovider -q
$env:HARNESS_INTEGRATION = '1'
$env:HARNESS_SYSTEM_URL = 'http://127.0.0.1:18206'
$env:HARNESS_TESTER_URL = 'http://127.0.0.1:18207'
$env:HARNESS_SENTINEL_URL = 'http://127.0.0.1:18212'
$env:HARNESS_EVIDENCE_DIR = 'artifacts/phase4-final-review/adapters'
& $python -X utf8 -B -m pytest tester-service/tests/test_http.py -q -p no:cacheprovider --basetemp artifacts/phase4-final-review/adapters-tmp --junitxml artifacts/phase4-final-review/adapters.xml
& $python -X utf8 -B scripts/check_phase4_runtime.py --project $harness --docker $docker --base-url http://127.0.0.1:18206 --evidence-dir artifacts/phase4-final-review
& $python -X utf8 -B scripts/check_phase4_runtime.py --project $harness --docker $docker --base-url http://127.0.0.1:18206 --evidence-dir artifacts/phase4-final-review/repeated
& $python -X utf8 -B scripts/check_autograder_runtime.py --project $harness --docker $docker --tester-url http://127.0.0.1:18207 --timeout-port 18208 --unsafe-port 18213 --evidence-dir artifacts/phase4-final-review/adapters
$env:TEST_API_PORT = '18226'
& $docker compose -p $deployment -f cra-service/docker-compose.test.yml up --build -d --wait --wait-timeout 240
Get-Content -Raw scripts/check_startup_schema.py | & $docker compose -p $deployment -f cra-service/docker-compose.test.yml exec -T api python -
Get-Content -Raw scripts/check_release_reset_race.py | & $docker compose -p $deployment -f cra-service/docker-compose.test.yml exec -T -e CRA_RACE_TEST_ALLOW_RESET=1 api python -
Get-Content -Raw scripts/check_local_rollback.py | & $docker compose -p $deployment -f cra-service/docker-compose.test.yml exec -T api python -
& $python -X utf8 -B scripts/check_deployment_runtime.py --project $deployment --docker $docker --evidence-dir artifacts/phase4-final-review/deployment-runtime
& $python -m ruff check cra-service tester-service scripts
& $python -m ruff format --check cra-service tester-service scripts
& $python -m mypy
& $python -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/phase4-final-review/full
& $python -X utf8 -B -c "import yaml; from openapi_spec_validator import validate_spec; validate_spec(yaml.safe_load(open('docs/autograder-openapi.yaml', encoding='utf8')))"
git diff --check
```

These paths identify the actual run; use new unique projects/ports/temp paths for
later execution. Current GitHub Actions runs the expanded tests/static checks and
both runtime scripts; it has not run on this uncommitted revision. The original
base's passed workflow is not represented as Phase 4 CI success.

## Git review and remaining next steps

Candidate files are reviewed for credentials, keys, local environment files,
generated evidence, DBs and unrelated artifacts. Public dummy passwords in isolated
test Compose and negative-test strings are synthetic, not cloud credentials.
`.gitignore` excludes environment variants/key/DB/log artifacts while retaining
safe examples. Shared OpenAPI/fixtures, original HTTP file/conftest and local
development Compose have no diff. No file is deleted or reorganized.

All **36 intended files** appear in Git's working diff: **10 new, 26 modified**.
New files are registered using `git add -N` (intent-to-add), so none is hidden as
untracked/ignored. No content is staged and no commit exists for these changes.
Key-pattern/manual review found no real credentials; only tracked environment
examples exist, and no generated evidence, DB or temporary artifact is included.
Final `git diff --check` is clean. All **54 pre-existing containers** retained
their IDs/images/mounts/running states and all **11 pre-existing volumes** remain.
Only the two new verification stacks were stopped; their volumes are retained.
See `artifacts/phase4-final-review/preservation.json`.

Complete inventory (includes the original Phase 4 work and these review fixes):

```text
.github/workflows/ci.yml
.gitignore
README.md
cra-service/Dockerfile
cra-service/autograder/config.py
cra-service/autograder/runner.py
cra-service/docker-compose.test.yml
cra-service/main.py
cra-service/phase4.py
cra-service/test_autograder.py
cra-service/test_phase4_api.py
cra-service/test_phase4_unit.py
cra-service/timestamps.py
docs/autograder-interface.md
docs/autograder-openapi.yaml
docs/decisions.md
docs/dependency-track-integration-plan.md
docs/deployment-google-cloud.md
docs/deployment-phase4.md
docs/deployment-tester-google-cloud.md
docs/models.md
docs/phase3_status.md
docs/phase4-evidence-draft.md
docs/phase4-final-review.md
docs/phase4-implementation.md
docs/project_context.md
docs/testing.md
pyproject.toml
scripts/check_autograder_runtime.py
scripts/check_contract.py
scripts/check_phase4_runtime.py
tester-service/.env.example
tester-service/Dockerfile
tester-service/docker-compose.test.yml
tester-service/tests/test_core.py
tester-service/tests/test_http.py
```

Next: review these changes; approve commit/push separately; require the new CI
run; settle source delivery/dataset/pod policies; then authorize a safe rollout
and grading-reset window explicitly. Do not deploy a fixture-only source while
claiming complete production Phase 4. Hosted response evidence, source integration,
cross-team results and per-teammate report contributions remain outstanding.
