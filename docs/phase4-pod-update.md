> Additional Q6.1 target-selection checks/documentation: [cross-team guide](phase4-cross-team-testing.md). The789/353 results below precede these additional offline checks; portable suite remains353. No public cross-team run occurred.

# Phase 4 pod decision implementation and verification

November 1, 2026. Local working tree on base
`ad42a439b81fdfd42ab50e44cea4c53717d07769`; no new commit, push, cloud changes or
deployed results. This report supersedes the earlier final review/evidence draft
where policies, source choice or counts differ.

## Authority and comparison

The attached Phase 4 assignment, Phase 2 requirements/ACs and architecture plan,
the unchanged OpenAPI 1.0.0, existing implementation and the supplied conversation
were reviewed. The conversation documents Team 6 questions and Team 2 replies.
The user authorizes these local changes. It does **not** document finalized Team6
approval, completed fixture reviews or instructor acceptance of an OSV scope change.

| Decision | Before | Current implementation / verification |
|---|---|---|
| 1. Timestamp handling | Already accepted Z/offsets and normalized UTC | Retained strict aware RFC3339, numeric offsets including -00:00, microseconds; naive400. Added mutation offset/fraction regression cases. |
| 2. Submissions | Equality/late statuses correct, but duplicates and N/A submissions accepted | Duplicate409 CONFLICT under incident row lock; N/A400. Equality/met/pending and late-overdue assertions preserved; rejected writes leave state intact. |
| 3. Incident times | Future/fix replacement/voluntary behavior mostly correct; no awareness chronology guard | Fix/submission before awareness400; future allowed; replacement and voluntary N/A covered. Latest attribution retained, no complete audit/history claimed. |
| 4. CVE validation | Query path format checked, incident CVE only typed | Malformed query/incident CVE400 INVALID_REQUEST; valid unknown incident CVE accepted even during source outage. No existence lookup. |
| 5. PURL identity | Fixture exact whole-string equality | Strip qualifiers/subpaths, preserve exact version; no PURL means no match. Four new HTTP regressions plus OSV package/version cases. |
| 6. Source reset | Reset removed row; omitted records preserved prior dataset | Reset available/empty; PUT always replaces entire dataset. Actual disposable DB guard before truncation; OSV history unaffected. |
| 7. AC04 evidence | Existing tests already used set equality | Exact release/component sets and 100% precision/recall retained; reviewer worksheet prepared with pending names/dates/sign-off. |
| 8. Source/alerts | Only synthetic fixtures, unimplemented Dependency-Track plan | Real OSV fetch/import/raw storage/aliases/provenance/freshness/local matching, separately tested with an upstream record. Deadlines still calculated on read; no push alerts. Coverage/refresh limits below. |

Source architecture is recorded in [ADR0001](adr-0001-osv-snapshots.md). REQ03/04 and
AC04/05 are not reduced. REQ05/06 are locally verified, including chronology,
offsets, classification, independent exact UTC deadlines and concurrent duplicates.
REQ07 reports/REQ08 complete audit remain Phase5 work.

## Contract proposal and remaining coordination

Original `docs/openapi.yaml` is byte-identical. The separate
[`openapi.phase4-proposed.yaml`](openapi.phase4-proposed.yaml) is **unapproved**:
adds duplicate submission409, malformed-CVE400, missing test-control negative
responses, and descriptions for aware times, chronology, equality, fixture
replacement and disposable resets. It does not add public OSV ingestion routes.
Runtime errors use the shared Error envelope; additional responses are explicitly
recorded as undocumented extensions when absent from the original YAML.

Finalize shared response/code additions with Team6, confirm the architectural
deviation with the appropriate pod/instructor authority, and obtain actual reviews
using [the fixture worksheet](ac04-fixture-review.md). Exact error mappings such
as CONFLICT must not be described as finalized pod agreement merely because they
are implemented locally.

## OSV delivery and honest limits

This is not renamed fixture data. Operator fetch downloads official OSV JSON/ZIP
over verified HTTPS, records scope/UTC/upstream SHA, validates a pinned official
schema, and requires reviewed file hash plus explicit approved database for import.
A transactional generation switch preserves prior active data on SQL failure.
Raw documents, CVE aliases, immutable generation metadata and an active pointer
are in PostgreSQL. API requests query local storage without outbound downloads.

Explicit versions, SEMVER and PyPI ECOSYSTEM ranges are implemented. Native
non-PyPI ECOSYSTEM and GIT graph comparisons remain unsupported and return503
when needed. No missing/stale source silently becomes an empty successful result.
Default seven-day wall-clock freshness cannot be extended by the injected clock.
Read [operations/limits](osv-snapshots.md) before selecting a production feed.

Real HTTPS-fetched `GHSA-j8r2-6x86-q33q` resolves CVE-2023-32681: requests2.30.0
matches and2.31.0 does not. This is **one selected-record proof**, not full-ecosystem
acceptance or a production refresh deployment. Bundle SHA256:
`6880e5fd0be5cfbc6a498abe2aba5d7631840d5ed2f38daa41a2a8ac2d8cec82`.
Raw source/schema hashes, fetch/import UTC times and actual matches are in ignored
`artifacts/phase4-pod-update/final/osv-runtime.json`.

Full ecosystem ZIP ingestion at representative size, multi-ecosystem assembly,
coverage agreement, refresh scheduling/monitoring/retention and hosted latency
remain incomplete/unverified. No new cloud service, API key, resource or expense
was created. Existing Cloud SQL roles/secrets can support an approved OSV runtime;
any refresh job and database/coverage choice need deployment review.

## Test preservation and actual results

All157 original HTTP cases and `conftest.py` are byte-identical, with matching
pre-task SHA256s. All154 earlier Phase4 scenarios remain covered. Of their case
identifiers,150 are identical; two policy tests were renamed and two rollover
parameters were corrected to place fix after awareness. Reset/source replacement
oracles changed as requested; duplicate-success expectations now assert409 and
unchanged data, not weakened assertions.42 new HTTP cases yield196 Phase4 cases.
Evidence: `artifacts/phase4-pod-update/test-case-comparison.json`.

| Check | Actual final result |
|---|---|
| Complete local pytest excluding opt-in HTTP adapter integration file | **789 passed**,0 failed/errors/skipped,62.70s;157 original+196 Phase4+436 other |
| Real HTTP adapter integration file | **8 passed**,182.34s |
| System adapter real child | **353 passed**,0 failures/errors/skips;54.541s |
| Tester adapter real child | **353 passed**,0 failures/errors/skips;56.333s |
| Phase4 restart/SQL rollback/duplicate/DB guard/long-PURL checks | **5 passed** |
| Report DB isolation/restart/interruption/timeout/reset refusal | **6 passed** |
| OSV raw ingestion/atomic rollback/freshness/guards/restart/storage failure/real advisory | **7 passed** |
| Concurrent startup/legacy preservation/readiness/schema rollback | **6 checks passed** |
| Release creation concurrent-reset regression | **2 cases passed** |
| Nested SBOM forced SQL failure | Passed: prior25 components retained, sanitized500, no idle transactions |
| Deployment runtime | Passed: default8080, PORT9090, invalid PORT, DB outage health/recovery, cold-start retry, API/DB persistence, graceful stop |
| Ruff lint / formatting | Passed;43 Python files formatted |
| mypy | Passed;13 production source files |
| OpenAPI | Original shared, proposed candidate and adapter extension valid;17 shared operations and25 locked fixture packages checked |
| Protected data/files | All8 protected-file hashes identical; all67 pre-existing container identities/images/mount mappings/states and13 volumes preserved |
| Secrets/artifacts/diff review | No secret-format/generated-file findings; `git diff --check` passed; nothing committed/staged for commit |

Pytest emitted one existing third-party `dateutil` deprecation warning. Local
Docker build SHA defaults to `unknown`; these are working-tree results, not proof
of a new committed SHA. Ignored `intended-files.json` records source SHA256s.
Future approved builds must pass the actual approved commit SHA for hosted evidence.
Both runners validate real JUnit test identities, files, AC groups and counts;
the integration also requires a deliberately broken target to report real failures.

## Exact validation commands

PowerShell repository root, existing `.venv` activated. All destructive checks
used newly created local projects only. No original/deployed database was used.
Docker executable was passed by its installed absolute path where `--docker` is
shown. Fresh harness ports18406/18407/18412/18414 and project
`cra-phase3-autograder-osv-pod-20261101-02` were used. New deployment project was
`cra-phase3-deployment-osv-pod-20261101`, loopback18426.

```powershell
python -X utf8 -B -m pytest cra-service tester-service/tests --ignore=tester-service/tests/test_http.py --allow-reset --base-url http://127.0.0.1:18406 --capture-http-bodies --evidence-dir artifacts/phase4-pod-update/final --junitxml artifacts/phase4-pod-update/final.xml -p no:cacheprovider -q
$env:HARNESS_INTEGRATION='1'
$env:HARNESS_SYSTEM_URL='http://127.0.0.1:18406'
$env:HARNESS_TESTER_URL='http://127.0.0.1:18407'
$env:HARNESS_SENTINEL_URL='http://127.0.0.1:18412'
$env:HARNESS_EVIDENCE_DIR='artifacts/phase4-pod-update/adapters'
python -X utf8 -B -m pytest tester-service/tests/test_http.py -p no:cacheprovider --junitxml artifacts/phase4-pod-update/adapters.xml -q
python -X utf8 -B scripts/check_phase4_runtime.py --project cra-phase3-autograder-osv-pod-20261101-02 --docker $docker --base-url http://127.0.0.1:18406 --evidence-dir artifacts/phase4-pod-update/final
python -X utf8 -B scripts/check_osv_runtime.py --project cra-phase3-autograder-osv-pod-20261101-02 --docker $docker --base-url http://127.0.0.1:18414 --real-snapshot artifacts/phase4-pod-update/real-osv-snapshot.json --evidence-dir artifacts/phase4-pod-update/final
python -X utf8 -B scripts/check_autograder_runtime.py --project cra-phase3-autograder-osv-pod-20261101-02 --docker $docker --tester-url http://127.0.0.1:18407 --timeout-port 18408 --unsafe-port 18413 --evidence-dir artifacts/phase4-pod-update/adapters
Get-Content -Raw scripts/check_startup_schema.py | & $docker compose -p cra-phase3-deployment-osv-pod-20261101 -f cra-service/docker-compose.test.yml exec -T api python -
Get-Content -Raw scripts/check_release_reset_race.py | & $docker compose -p cra-phase3-deployment-osv-pod-20261101 -f cra-service/docker-compose.test.yml exec -T -e CRA_RACE_TEST_ALLOW_RESET=1 api python -
Get-Content -Raw scripts/check_local_rollback.py | & $docker compose -p cra-phase3-deployment-osv-pod-20261101 -f cra-service/docker-compose.test.yml exec -T api python -
python -X utf8 -B scripts/check_deployment_runtime.py --project cra-phase3-deployment-osv-pod-20261101 --docker $docker --evidence-dir artifacts/phase4-pod-update/deployment
python -m ruff check cra-service tester-service scripts
python -m ruff format --check cra-service tester-service scripts
python -m mypy
python -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/phase4-pod-update/final
python -X utf8 -B -c "import yaml; from openapi_spec_validator import validate_spec; validate_spec(yaml.safe_load(open('docs/autograder-openapi.yaml',encoding='utf8')))"
git diff --check
```

Both new stacks were built with `docker compose ... up --build -d --wait
--wait-timeout240`, and stopped afterward. No containers or volumes were deleted.
The first local OSV stack is also stopped and retained. Original CRA containers
remain in their original runtime states; no queries/migrations/resets touched
`cra_phase3`. The preservation script's initial comparison needed normalization
of differently shaped mount metadata; the normalized check passed without changing
any pre-existing container. Initial whitespace scan found old Markdown trailing
spaces in project_context; these were removed before final checks.

## Readiness

No known critical local implementation defect remains. Changes are ready for
review and an approved commit, with the shared contract proposal explicitly
separate. They are **not a claim of complete production/deployment readiness**.
Before deployment: approve shared response additions, obtain actual fixture review,
select OSV scope/coverage/refresh operations, then build both images at the same
approved SHA and follow [paired rollout](deployment-phase4.md). Fixture grading
and production OSV are separate modes; no reset-based suite against production.
Direct test-control calls bypass cooperating adapter locks, so schedule exclusive
grading windows. No GitHub Actions run for these uncommitted changes is claimed.

## Complete intended file inventory

56 intended files relative to HEAD, including the prior Phase4 increment and
additional Q6.1 tests/configuration/docs. No deletions or moves. New files remain
untracked until approved staging; no new commit or staged content was created.

```text
.gitattributes
.github/workflows/ci.yml
.gitignore
README.md
cra-service/Dockerfile
cra-service/autograder/config.py
cra-service/autograder/runner.py
cra-service/docker-compose.test.yml
cra-service/main.py
cra-service/osv_source.py
cra-service/phase4.py
cra-service/purl_matching.py
cra-service/requirements.txt
cra-service/test_autograder.py
cra-service/test_osv.py
cra-service/test_phase4_api.py
cra-service/test_phase4_unit.py
cra-service/timestamps.py
cra-service/vendor/osv/LICENSE
cra-service/vendor/osv/SOURCE.json
cra-service/vendor/osv/schema.json
docs/ac04-fixture-review.md
docs/adr-0001-osv-snapshots.md
docs/autograder-interface.md
docs/autograder-openapi.yaml
docs/decisions.md
docs/dependency-track-integration-plan.md
docs/deployment-google-cloud.md
docs/deployment-phase4.md
docs/deployment-tester-google-cloud.md
docs/models.md
docs/openapi.phase4-proposed.yaml
docs/osv-snapshots.md
docs/phase3_status.md
docs/phase4-cross-team-testing.md
docs/phase4-evidence-draft.md
docs/phase4-final-review.md
docs/phase4-implementation.md
docs/phase4-pod-update.md
docs/phase4-q61-results-template.md
docs/project_context.md
docs/testing.md
pyproject.toml
scripts/check_autograder_runtime.py
scripts/check_contract.py
scripts/check_osv_runtime.py
scripts/check_phase4_runtime.py
scripts/osv_snapshot.py
tester-service/.env.example
tester-service/Dockerfile
tester-service/cross-team.env.example
tester-service/docker-compose.test.yml
tester-service/tests/init-databases.sql
tester-service/tests/test_core.py
tester-service/tests/test_cross_team_selection.py
tester-service/tests/test_http.py
```
