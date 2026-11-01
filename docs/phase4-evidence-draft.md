> Phase4 Q6.1 addition: see [phase4-q61-results-template](phase4-q61-results-template.md). Bidirectional target support is verified offline; actual public runs and live allowlist configuration remain pending authorization.

> **Current evidence addendum, November 1, 2026:** [phase4-pod-update.md](phase4-pod-update.md) supersedes the earlier results and source conclusions below. The local suite now has 353 portable HTTP cases; real OSV snapshot ingestion/matching is implemented and checked with one actual upstream advisory. See the [ADR](adr-0001-osv-snapshots.md) for incomplete coverage and approval status. All remaining sections below are the historical pre-pod-update draft, retained for provenance, and must be revised from this addendum before submission. No hosted Phase 4 or Team 6 verification is claimed.

# ECE 30861 Team 2 Phase 4 evidence draft

Prepared November 1, 2026. **Local implementation, not a final deployed submission.**

**Superseding final review:** `phase4-final-review.md` records 689 tests passed,
both 311-case runners and stricter report/oracle safety checks. Its commands and
results supersede the initial 684-test snapshot in section 4 below. Production
Dependency-Track remains incomplete; see `dependency-track-integration-plan.md`.
Repository base: `ad42a439b81fdfd42ab50e44cea4c53717d07769`, plus uncommitted Phase 4
changes. Final cover-page commit/tag and deployed revision: **pending approval**.
User-reported existing deployment: system `cra-phase3-api`, tester
`cra-phase3-tester`, project `cra-vulnerability-service`, region `us-central1`.
The historical 157/157 public result is supplied by the user; it is not a test
of this new code. The base workflow passed at
[run 40375076748](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/40375076748);
there is **no Phase 4 remote CI run** before commit/push approval.

Assignment source: user-supplied *Software Engineering Phase 4.pdf*, all nine
pages/sections reviewed; Phase 2 report sections 3–9 and unchanged shared OpenAPI
1.0.0 establish behavior. The PDF's older Phase 3 references in Q1.2/Q4.1/Q6.1 and
“next Phase 4” in Q7.3 require instructor interpretation; both literal and current
milestone comparisons are addressed below without assuming a scope reduction.

## 1. Delivered increment and comparison with Phase 2

Release engineers can query stored component inventories against a configured
test CVE dataset and see releases grouped by current UTC support status. Source
failure and unknown identifiers produce distinct errors, avoiding false empty
results. Incident responders can persist mandatory/voluntary cases with their
awareness time, actor and rationale, record fixes/submissions, and inspect three
independent deadlines. These capabilities support the project interpretation of
CRA vulnerability handling and Article 14(2) reporting; a person still decides
reportability and submits reports to authorities [1]. This is a deterministic
course/test increment, with no claimed live vulnerability scanning integration.

| Requirement | Local delivery | Demonstrated by / missing |
|---|---|---|
| REQ-01 | Preserved | Original AC-01 regression cases |
| REQ-02 | Preserved | Original AC-02/03 regression cases and protected 25-component fixture |
| REQ-03 | Complete deterministic test behavior; production integration partial | AC-04 five synthetic CVEs, exact affected sets/grouping/latency; pod manifest and Dependency-Track integration still missing |
| REQ-04 | Deterministic source/error behavior delivered | AC-05 known-unaffected/unknown/outage; no real Dependency-Track outage test |
| REQ-05 | Implemented and locally verified | AC-06 mandatory/voluntary, actor, exact UTC awareness, invalid inputs; human rationale inspection still required |
| REQ-06 | Implemented and locally verified | AC-07 exact deadlines, stage statuses, rollover/offsets, invalid requests, restart persistence |
| REQ-07 | Deferred Phase 5 | Stage report-data storage/generation not implemented |
| REQ-08 | Partial supporting persistence/attribution only | Persistent case/submission rows; immutable audit/history/complete AC-09/10 remain Phase 5 |

Phase 2 section 6.1's Phase 3 release/SBOM increment remains intact and all 157
original HTTP assertions are preserved. Section 6.2's Phase 4 query/fault-injection/
incident/deadline increment is now implemented for deterministic testing. Section
7.2 selected Dependency-Track and section 7.3 described a Compose host with extra
storage; actual Cloud Run/Cloud SQL lacks that integration. The compatible
test-source seam is implemented, while production matching and dataset agreement
remain explicit limitations, not an unapproved replacement feed [2].

## 2. Deployment and operation

Existing user-reported addresses (not changed or destructively tested here):

- System: `https://cra-phase3-api-456725640364.us-central1.run.app`
- Tester: `https://cra-phase3-tester-456725640364.us-central1.run.app`
- Shared contract: repository `docs/openapi.yaml`; generated runtime `/docs` is
  supplementary and does not replace the pod document.

Deployment of the new pair, availability window/registry update, exact SHA/image
digest/revision, startup/cold-start latency, Cloud SQL connectivity, public probes,
operational costs and runtime permissions must be verified after approval.
`deployment-phase4.md` gives Console steps, build/deploy commands, exclusive test
window, secrets/role checks and rollback. Both roles preserve their current URLs;
900-second HTTP/600-second child limits and existing shared execution lock remain.
Cloud Run request timeout does not itself terminate work; the runner separately
terminates timed-out children [3].

Domain data stays in disposable `cra_grading`; reports/locking stay in separate
`cra_autograder`. The original `cra_phase3` remains untouched, and startup refuses
to initialize it. New schema creation is additive and transaction-locked [4].
No new secret is required for synthetic CVEs; existing Secret Manager DSNs and
Cloud SQL socket/least-privilege identities are retained. A real Dependency-Track
deployment requires a separate reviewed resource and API-key plan [2].

**Missing deployed observability evidence:** sanitized Cloud Logging excerpt
with request ID, route/status/latency and actor; a real source-unreachable 503;
revision/build mapping; actual request/DB metrics and resource usage. Local logs
and injected SQL failures prove local behavior only. Backups/alerts/p95 dashboards
mentioned in Phase 2 have not been verified here and must not be claimed.

## 3. Complete shared-interface operation status

All rows refer to **local code/verification**. Only the first four operations and
reset/clock were in the previously deployed Phase 3 domain increment; new routes'
hosted status is pending. Generated `operation-status.json` records observed
statuses and route presence; unexercised responses are not inferred as tested.

| Shared operation | REQ | Local implementation/conformance | Phase 4 deployed |
|---|---|---|---|
| POST `/api/v1/releases` | 01,08 | Yes; 201/400/409 schema checked | Pending regression |
| GET `/api/v1/releases/{releaseId}` | 01 | Yes; 200/404 schema checked | Pending regression |
| PUT `/api/v1/releases/{releaseId}/sbom` | 02,08 | Yes; 200/400/404 schema checked, atomic | Pending regression |
| GET `/api/v1/releases/{releaseId}/components` | 02 | Yes; 200/404 schema checked | Pending regression |
| GET `/api/v1/vulnerabilities/{cveId}/affected-releases` | 03,04 | Yes in test mode; 200/404/503 schema checked; invalid path 400 is not enumerated in YAML | Pending |
| POST `/api/v1/incidents` | 05,06,08 | Yes; 201/400 schema checked | Pending |
| GET `/api/v1/incidents/{incidentId}` | 05,06 | Yes; 200/404 schema checked | Pending |
| PATCH `/api/v1/incidents/{incidentId}` | 06,08 | Yes; 200/400/404 schema checked | Pending |
| POST `/api/v1/incidents/{incidentId}/submissions` | 06,08 | Yes; 201/400/404 schema checked | Pending |
| PUT `/api/v1/incidents/{incidentId}/report-data/{stage}` | 07,08 | No; Phase 5, success/error conformance not claimed | Deferred |
| GET `/api/v1/incidents/{incidentId}/reports/{stage}` | 07 | No; Phase 5 | Deferred |
| GET `/api/v1/audit-logs` | 08 | No; Phase 5 | Deferred |
| PATCH `/api/v1/audit-logs/{eventId}` | 08 | No; required immutability 405 not implemented | Deferred |
| DELETE `/api/v1/audit-logs/{eventId}` | 08 | No; required immutability 405 not implemented | Deferred |
| POST `/api/v1/test/reset` | Test | Yes; 204, now clears incidents/submissions/source too | Pending regression |
| PUT `/api/v1/test/clock` | Test | Yes; 200; invalid 400 Error is a disclosed YAML omission | Pending regression |
| PUT `/api/v1/test/vulnerability-source` | Test | Yes; 200; invalid 400 and unsafe-config 503 Error omitted by YAML | Pending |

Contract version remains 1.0.0, unchanged. `phase4.py` is installed into existing
FastAPI, using the existing psycopg2 transaction/clock helpers. Queries join
persisted component PURLs to test records; incident routes lock rows and calculate
statuses from stored timestamps. Models and decisions describe local ambiguity
choices. There is no newly documented pod/instructor approval of duplicate,
source-update or anchorless-submission semantics.

## 4. Automated validation and actual evidence

Portable HTTP count changes from **157 to 311**, adding **154** cases in
`test_phase4_api.py` without editing `test_api.py` or `conftest.py`. The hosted
runner expects 311, classifies AC-01–07, rejects incomplete/skip/error runs, and
retains actual JUnit outcomes and redacted HTTP examples [5]. The separate
`test_phase4_unit.py` adds **141** non-destructive cases for timestamp fields,
source guards, retained DB refusal, AC mapping and collection accounting.

| AC | Tests/oracle | Local evidence |
|---|---|---|
| AC-01/02/03 | All original 157 tests and prior unit cases | Full regression XML and unchanged-file diff |
| AC-04 | `test_ac04_five_cves_exact_precision_recall_grouping_and_latency` (5) and `test_ac04_support_group_uses_current_utc_clock` | Exact synthetic release/PURL sets, patched isolation, supported grouping, <10-second assertions |
| AC-05 | Known unaffected/unknown/outage/recovery, invalid/atomic source changes, reset | 200 vs explicit 404/503; <15-second combined scenario |
| AC-06 | Create/read mandatory/voluntary, invalid/missing fields, invalid timestamp fixture and 13 valid offset cases | Exact actor, classification, awareness UTC and rationale preservation; human inspection pending |
| AC-07 | Exact 24h/72h/14d sequence, +/-1-second boundaries, late filing, 3 rollover cases, invalid mutations/stages, reset | Fixed explicit UTC oracles with zero-second tolerance; restart/rollback/concurrency runtime checks |

Actual local runs use newly created disposable Docker projects. Initial runs used
`cra-phase3-autograder-phase4-20261101-01` on loopback 18106/18107. Final schema
and suite checks use **`cra-phase3-autograder-phase4-20261101-02`**, on loopback
**18116/18117**, from a second empty volume. Existing deployment runtime checks
use a third fresh project, `cra-phase3-deployment-phase4-20261101`, at 18126.

- Before changes: **232 non-destructive tests passed**.
- Final regression/acceptance run: **684 passed**, 0 failures/errors/skips, 53.68 seconds;
  `artifacts/phase4-review/final.xml`. One pre-existing dateutil deprecation
  warning on host Python 3.12; Docker uses Python 3.11.
- Real HTTP adapter verification: **8 passed**, including both 311-case children,
  required AC groups, real failing target, concurrent-run rejection, and redirect
  sentinel receiving zero destructive requests. The final rerun passed in 151.22
  seconds; system child 311/311 in 43.780 seconds, tester child 311/311 in 49.611
  seconds. All 311 checks on each role have actual request/response examples.
- Five Phase 4 runtime checks passed: exact incident/source persistence across
  API restart; forced SQL submission failure rolls back/sanitizes; three concurrent
  stage writes retain all rows/actors; wrong/retained source approval refused;
  long valid PURL ingestion/matching preserved using a hash equality index.
- Six existing adapter runtime/storage checks passed: ordinary-role permissions,
  separate report persistence through reset/restart, hard interruption recovery,
  actual child timeout, and wrong-DB reset refusal.
- Both Docker images built successfully. Ruff lint/format, mypy (11 production
  files), shared and extension OpenAPI 3.1 validation passed. Final diff check is
  clean, including all eight new files; a trailing blank-line issue was fixed.

All 33 pre-existing container IDs/images/mounts/running states and all eight
pre-existing volumes match the recorded pre-test inventory. Only this session's
new stacks were stopped; all three new volumes are retained. No existing DB or
volume was reset/deleted, and no cloud command/destructive public request ran.
Preservation proof: `artifacts/phase4-review/preservation-result.json`. Candidate
files contain no detected private keys/cloud credential files/generated artifacts;
shared contract/fixtures and both original HTTP test files have no Git diff.
The final recorded lookup maximum was 0.016 seconds across 23 local responses,
not a hosted p95 or large-load benchmark.

Additional existing integration checks passed: six schema/startup checks including
six concurrent initializers and preserving seeded legacy rows, two deterministic
release/reset-race cases, and real PORT/health/DB-outage/retry/restart checks.
The SBOM SQL rollback command was initially misconfigured: its temporary trigger
was installed in fresh `cra_test` while the running API used fresh `cra_grading`,
so the intended failure was not injected and the assertion failed. No application
bug or retained DB was involved. Rerunning in the matching third test project's
API/DB passed: 25 old components retained, sanitized 500 and no idle transaction.
See `sbom-rollback-corrected.log`; the failed attempt remains disclosed here.

Exact commands are in `deployment-phase4.md` and `testing.md`. Runtime evidence:
`artifacts/phase4-review/phase4-runtime.json` and
`artifacts/phase4-review/autograder/runtime-results.json`. Full JUnit, operation
observations/status, SHA-256 of protected inputs, and UTC HTTP bodies are under
`artifacts/phase4-review/`. Artifacts are ignored and must not be committed.
Version is recorded as base SHA **plus dirty worktree**, not falsely assigned a
new target SHA. Docker BUILD_SHA is unknown in local builds, not a deployed SHA.

Q4.1 asks to confirm deployed conformance despite saying suite build instructions
are unnecessary: deployed Phase 4 conformance remains pending. Q4.3/4.4 current
local checks are not a CI URL. CI is configured to run new local tests/runtime
checks on push/PR, but branch protection and deployment gates are human/repository
settings, not proven by workflow YAML alone.

## 5. Updated models and code consistency

`models.md` contains the implemented architecture/request flow, incident/source
ER model, CVE three-outcome flow and parallel deadline state model, with each
Phase 2 model's update status. Source DDL/routes and HTTP oracles were compared
to those models; no external scanner, workflow engine, audit table or reminder
service is shown as implemented. Existing SBOM flow/release ER remains valid.
The Phase 2 discrepancy corrected in the model is Dependency-Track/Compose-host
being shown as delivered infrastructure: actual code uses a test fixture source
and user-reported Cloud Run/Cloud SQL; production source integration remains open.

## 6. Cross-team testing and unresolved specification details

**Not run in this task; do not fill with invented results.** Coordinate exclusive
reset windows and the shared Phase 4 dataset before both directions:

| Direction | Date/SHA/target | Run/pass/fail | Coverage/evidence/problem owner |
|---|---|---|---|
| Team 2 expanded suite -> Team 6 service | Pending | Pending | API/AC and component/model coverage pending; obtain peer coverage evidence for code coverage |
| Team 6 full suite -> Team 2 service | Pending | Pending | Save their full report, tested revisions, mismatches and owner |

Provide real code/component/system-model coverage for both directions as the
assignment asks; black-box pass counts alone are not source-code coverage.
No coverage percentage or prior Phase 3 result is relabeled as Phase 4 evidence.
Open questions in `decisions.md`: duplicate stage submissions; filings before fix
anchor; fix correction/chronology; optional records persistence/duplicate CVEs;
exact PURL identity versus ranges; negative test-control schemas; and the actual
five-CVE ground truth. Missing final-anchor status follows the Phase 2 example.
Record Team 6's actual decision date/channel and staff approval where required
before any shared-contract edit. No shared file has been changed here.

## 7. Limitations, unfinished scope and next-phase risks

Changes: preserved REQ-01/02; deterministic REQ-03/04 routes; persistent REQ-05
cases and REQ-06 deadline calculation; expanded guarded test service and models.
Incomplete: production vulnerability integration/shared-dataset acceptance,
hosted Phase 4 validation/cross-testing, and Phase 5 REQ-07/08/AC-08–10.

| Limitation | Severity / affected scope | Workaround and next action |
|---|---|---|
| LIM-01 Dependency-Track absent | High; production REQ-03/04 | Test fixture source only; provision planned service/key/sync or obtain explicit approved revision before production claims |
| LIM-02 Shared Phase 4 manifest absent | High; AC-04 precision/recall evidence | Jointly review manifest, freeze fixtures and rerun both teams before Phase 4 submission |
| LIM-03 New code not deployed/CI-run | High; operational delivery | Approve commit/push, verify current CI, paired rollout and own hosted suite |
| LIM-04 Duplicate/chronology/source semantics unresolved | Medium; cross-team compatibility | Team 6 discussion of local choices, no claimed agreement |
| LIM-05 Direct global test controls bypass adapter mutex | Medium; reset/clock/source interference | Exclusive windows; never target retained DB or unapproved systems |
| LIM-06 No stage reports/immutable audit | Expected Phase 5 gap; REQ-07/08 | Implement after Phase 4 review; do not treat ordinary attribution rows as audit events |
| LIM-07 Overload/large fixture performance not established | Medium; REQ-03 latency | Per-statement bounds/local small-set evidence only; measure hosted p95 with approved workloads |

Phase 2 Risk 1 (source precision/outage/resources) remains open for production;
deterministic failures and matching are now testable. Risk 2 (awareness meaning)
retains the supplied-user-timestamp rule; no legal inference was added. Deadline
drift risk is reduced by UTC arithmetic and restart tests, while pod-policy and
paired-version rollout are current risks. The Phase 5 milestone remains stage
reports/audit/full durability evidence; do not reduce shared scope unilaterally.

### Review inventory: all 36 changed files

Ten are new (Phase 4 module, timestamp helper, HTTP tests, unit tests, runtime
checker and five Phase 4 guides/reviews); 26 existing files are updated. No files are
deleted or moved. Existing local development Compose, runtime requirements and
both shared input directories are unchanged. The extension OpenAPI description
is updated; the shared `docs/openapi.yaml` is not.

```text
.github/workflows/ci.yml
.gitignore
README.md
cra-service/Dockerfile
cra-service/autograder/runner.py
cra-service/autograder/config.py
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
docs/deployment-google-cloud.md
docs/dependency-track-integration-plan.md
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
tester-service/Dockerfile
tester-service/.env.example
tester-service/docker-compose.test.yml
tester-service/tests/test_http.py
tester-service/tests/test_core.py
```

## 8. GenAI contributions — each teammate must complete their own account

This session used Codex for repository/PDF review, implementation, test scaffolding,
debugging, models/documentation and local verification. It did not use GenAI as a
runtime vulnerability or legal decision source. Verification used real pytest,
PostgreSQL/Docker, static/contract checks and protected-file diffs; no merge or
deployment occurred. A concrete correction in this session: the first local
deadline interpretation used pending without a fix; review of the Phase 2 example
corrected it to not_applicable, with acceptance tests updated before final review.
Another correction: Docker pytest root prefixes prevented per-case HTTP examples
from attaching; actual child reports exposed it and a regression check was added.

For **each teammate**, write 3–4 factual sentences covering tools/delegation,
personal verification, an actual error/correction, and adherence/deviation from
course agentic principles. Names/contributions/review claims are intentionally
not filled in by this draft. This session's tool output is supporting evidence,
not a substitute for each person's truthful account.

## 9. References

Accessed November 1, 2026. Cite the relevant section/provision when transferring
these references into the final report. Preserve numbering at first use.

[1] European Parliament and Council. “Regulation (EU) 2024/2847 (Cyber Resilience
Act).” October 23, 2024. Article 14(2), Article 15, Annex I Part II.
https://eur-lex.europa.eu/eli/reg/2024/2847/oj

[2] OWASP Dependency-Track. “REST API” and “Deploying Docker Container.” v4.14.
https://docs.dependencytrack.org/integrations/rest-api/ and
https://docs.dependencytrack.org/getting-started/deploy-docker/

[3] Google Cloud. “Configure request timeout for services.”
https://docs.cloud.google.com/run/docs/configuring/request-timeout

[4] PostgreSQL Global Development Group. “Explicit Locking,” section 13.3.5,
PostgreSQL 16. https://www.postgresql.org/docs/16/explicit-locking.html

[5] pytest developers. “Creating JUnitXML format files.” pytest documentation.
https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files

[6] FastAPI. “Handling Errors.”
https://fastapi.tiangolo.com/tutorial/handling-errors/ (400 mapping is our
existing application handler, not FastAPI's default behavior).

[7] Google Cloud. “Rollbacks, gradual rollouts, and traffic migration.”
https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration

[8] Psycopg. “Basic module usage,” transactions and connection context managers.
https://www.psycopg.org/docs/usage.html#with-statement
