# Phase 3 status

Current checkout is `main` at `7686edf2bbc007ca11c4f284d7e547821488f562` plus an
uncommitted release/reset race fix. Readiness/COPY changes are already saved.
The earlier [policy baseline CI run](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39157992256)
was verified successful; that does not verify this new fix, which has no CI run.

Saved public Google Cloud evidence for reported deployed SHA `7686edf` shows
**156 passed / 1 failed**, not full hosted acceptance. Clock normalization passed;
POST release returned 404. A reset between committed INSERT and follow-up lookup
reproduces that response locally. The fix captures the created row and UTC clock
inside its transaction, returning only after commit. An overlapping cloud reset
is plausible but not confirmed without server logs. See
[the investigation](testing.md#release-creation--concurrent-reset-investigation).

Current local verification: **297 passed**, including 157 Docker HTTP checks and
six new creation regressions. Two deterministic real HTTP/SQL reset interleavings
and the existing forced SBOM rollback check pass. No remote rerun, commit, push or
deployment of this fix occurred; original data/volumes and hosted evidence remain
unchanged. Cross-team execution and current cloud metadata were not inspected.

The previous supplied-policy increment passed **264 local tests** on port 18082.
The previous deployment-readiness increment passed **291 local tests**: 157 HTTP
checks against a new Docker API/PostgreSQL stack and 134 local tests (51 SBOM,
42 clock, 10 evidence, 15 startup, 8 health, 8 deployment-helper checks). Project
`cra-phase3-deployment-20261018` uses port 18083. Its HTTP report evidence contains
918 HTTP exchanges with UTC timestamps, captured bodies and base-SHA/dirty-source
provenance. A forced final nested INSERT failure preserves 25 prior components
and leaves no idle transactions. Details are in `testing.md`.

Approval status: the user supplied Team 6 questions and Team 2 answers, and
authorized compatible implementation. Team 2 acceptance is recorded; final Team 6
acknowledgement of exclusion/occurrence and wider exact-code proposals is not.
`decisions.md` distinguishes existing contract facts, supplied positions and
remaining proposals. Shared OpenAPI and Team 6 fixtures are unchanged.

## Acceptance mapping

| AC | Main automated checks | Current evidence |
|---|---|---|
| AC-01 / REQ-01 | `test_ac01_shared_release_cases`, `test_ac01_support_boundary`, `test_release_invalid_types_save_nothing` | Shared requests, rejection without a row, UTC boundary and rollover pass locally |
| AC-02 / REQ-02 | `test_ac02_shared_25_components_are_isolated`, `test_ac02_nested_inventory_counts_isolation_and_replacement` | Unchanged shared 25-component inventory plus 1.4/1.5/1.6 nested inventories pass; exact occurrence counts, metadata/tool exclusion, repeat replacement and release isolation checked |
| AC-03 / REQ-02 | `test_ac03_invalid_sbom_never_changes_inventory`, `test_ac03_unknown_release_stores_nothing`, `test_ac03_unknown_release_precedes_invalid_body`, `test_ac03_missing_nested_version_is_atomic`, `test_ac03_unsupported_spec_versions_are_atomic` | Malformed/invalid JSON, plaintext, unsupported versions, missing descendant versions and unknown releases rejected; both empty and populated inventory preservation checked |

Shared-case oracles come from unchanged release expectations, the SBOM's own
component tuples, the matching source lock file and OpenAPI schemas/statuses.
Added synthetic nested regressions use explicit flat expectations for small test
trees; they supplement the agreed shared fixture and are not claimed as reviewed
Team 6 data. No live CVE service is used. Error reasons have explicit automated
assertions and are retained in opt-in HTTP response artifacts for human review.
Capturing those artifacts does not constitute completed human review.

## Every shared operation

Paths have prefix `/api/v1`. “Observed” means local checks, not universal conformance.

| Operation | Requirement / phase | Implementation | Success / errors |
|---|---|---|---|
| POST /releases | REQ-01, future REQ-08 | Partial overall | 201/400/409 observed; audit absent; empty-string policy open |
| GET /releases/{releaseId} | REQ-01 | Implemented | 200/404 observed; UTC boundary checked |
| PUT /releases/{releaseId}/sbom | REQ-02, future REQ-08 | Phase 3 behavior implemented; audit later | 200/400/404 observed; recursive normalization and 1.4-1.6 support implemented under supplied policies; final proposal acknowledgement pending |
| GET /releases/{releaseId}/components | REQ-02 | Implemented under supplied inventory policy | 200/404 observed; shared flat and recursive inventories with repeated occurrences checked |
| GET /vulnerabilities/{cveId}/affected-releases | REQ-03/04, Phase 4 | No | Required 200/404/503 not implemented |
| POST /incidents | REQ-05/06/08, Phase 4 | No | Required 201/400 not implemented |
| GET /incidents/{incidentId} | REQ-05/06, Phase 4 | No | Required 200/404 not implemented |
| PATCH /incidents/{incidentId} | REQ-06/08, Phase 4 | No | Required 200/400/404 not implemented |
| POST /incidents/{incidentId}/submissions | REQ-06/08, Phase 4 | No | Required 201/400/404 not implemented |
| PUT /incidents/{incidentId}/report-data/{stage} | REQ-07/08, Phase 5 | No | Required 200/400/404 not implemented |
| GET /incidents/{incidentId}/reports/{stage} | REQ-07, Phase 5 | No | Required 200/404 not implemented |
| GET /audit-logs | REQ-08, Phase 5 | No | Required 200 not implemented |
| PATCH /audit-logs/{eventId} | REQ-08, Phase 5 | No | Required 405 not implemented |
| DELETE /audit-logs/{eventId} | REQ-08, Phase 5 | No | Required 405 not implemented |
| POST /test/reset | Phase 3 test control | Partial contract detail | Empty 204 and state clearing observed; exact reset defaults need agreement |
| PUT /test/clock | Phase 3 test control | Partial contract detail | 200 observed; existing 400 validation errors absent from shared OpenAPI |
| PUT /test/vulnerability-source | Phase 4 test control | No | Required 200 not implemented |

`scripts/check_contract.py` emits all operations and observed statuses to
`artifacts/operation-status.json`. It does not mistake route presence for complete
semantics or hosted availability. Contract version remains 1.0.0; no shared
contract or fixture changes were made.

The clock syntax defect is fixed locally: numeric strings, missing seconds,
invalid separators/offsets, invalid dates and surrounding whitespace are rejected.
Valid offset inputs, lowercase `t`/`z`, fractions, UTC rollover and leap-day dates
are tested. Existing microsecond datetime precision is unchanged. This does not
resolve the separate literal-`Z` policy or undocumented clock-error response.
The existing datetime representation still cannot represent leap-second instants;
this increment adds no new conversion policy for them.

## Deployment-readiness verification

| Item | Local evidence | GitHub / hosted status |
|---|---|---|
| Cloud Run PORT / signals | Same Dockerfile/image passes default 8080, override 9090, invalid-port rejection and graceful SIGTERM exit | Updated CI includes the check; not run on GitHub yet; Cloud Run unverified |
| Concurrent initialization | Six independent SQL connections initialize an empty schema concurrently; legacy VARCHAR upgrade preserves rows/timestamps; repeat TEXT startup avoids exclusive ALTER locks | Run in new local PostgreSQL test databases; no Cloud SQL instance exists |
| Retry, timeout and cleanup | Unit retries/deadlines/config rejection plus real advisory-lock timeout/recovery and incompatible-schema DDL rollback | New CI invokes `check_startup_schema.py`; cloud IAM/latency remain unverified |
| Health | Unit success/failure cases plus real HTTP ready 200/503 during DB stop/recovery, live 200 throughout; read-only UTC/timeouts checked | Probe configuration documented, not deployed |
| Persistence and local preservation | Synthetic release/inventory survives isolated API/DB restarts; original resources and database fingerprints match | Hosted restart verification remains required |
| Build and operations | Build-only `cloudbuild.yaml`; Console guide for socket DSN, secrets/IAM, cost, probes, verification and rollback | No Cloud Build trigger/build, image publication or resource creation executed |

See [the deployment guide](deployment-google-cloud.md) and
[executed test details](testing.md#google-cloud-deployment-readiness). Health
routes add no shared-contract operations or Phase 4/5 functionality.

## Limitations and remaining delivery work

| ID | Severity | Limitation / workaround | Next action |
|---|---|---|---|
| LIM-01 | Medium for cross-team readiness | Recursive inventory is implemented/tested. Metadata/tool exclusion and occurrence retention are still Team 2 proposals, without supplied Team 6 acknowledgement. Identical sibling duplicates remain schema-invalid. | Obtain acknowledgement and record the schema-valid duplicate boundary; do not weaken CycloneDX validation |
| LIM-02 | Medium | Version range and required descendant versions follow the supplied Team 2 acceptance. Metadata-only/absent-array input policy is still unspecified; existing behavior is retained. Old top-level records cannot recover omitted children without the original SBOM. | Retain final shared policy record; clarify absent-array behavior; coordinate any resubmission without resetting existing data |
| LIM-03 | Medium | Product/version nonempty prose conflicts with YAML; timestamp/error/reset details are incomplete. | Reconcile documents without unilateral API changes |
| LIM-04 | High for delivery | Saved public HTTPS run reaches the hosted target but has one failed POST; the race fix is verified only locally. Revision/image metadata, registry entry and two-way cross-team execution remain unverified. | Inspect logs, review/save/redeploy the fix only after approval; rerun hosted tests in an exclusive reset window and retain deployment provenance |
| LIM-05 | Medium | Readiness/COPY changes are committed through `7686edf`; the current release/reset race fix is locally verified but uncommitted and has no CI run. Branch protection was not changed. | Obtain commit/push approval for this fix and retain its own CI result |
| LIM-06 | Medium for reporting | No measured server code coverage or recorded human AC-03 review. HTTP evidence is available for that review. | Coordinate server coverage and human review; do not confuse runner coverage with service coverage |

Phase 4 remains REQ-03–06 / AC-04–07, including vulnerability fixture control.
Phase 5 remains REQ-07–08 / AC-08–10. The Phase 3 parsing and delivery gaps above
must not be silently deferred as a shared-scope reduction. Dependency-Track
performance/failure behavior remains an investigation before Phase 4.

Before submission: record both cross-team directions, counts, coverage limits,
failure owners, and one actual specification disagreement/resolution plan; include
deployed logs/version evidence and the web-service/test-runner registry locations.
Each teammate must supply their own factual GenAI-use and verification account.
No teammate activity, hosting result, or pod decision has been invented here.

## Remaining deployment and submission tasks

- [x] Implement and locally verify recursive inventory normalization and supplied 1.4/1.5/1.6 policy.
- [ ] Obtain final Team 6 acknowledgement of the remaining proposals and exact error-code mappings; resolve input/reset questions.
- [x] Retain successful main CI URL for committed policy baseline `f27cfd5`.
- [x] Implement PORT, concurrent-safe schema setup, bounded startup and minimal health routes; locally test them.
- [x] Add the Google Cloud Console guide and build-only configuration; update CI with isolated deployment checks.
- [x] Save deployment-readiness/COPY changes to main through `7686edf`.
- [ ] Review the new release/reset race fix, authorize saving/redeploying it, and verify its own CI run.
- [x] Select Google Cloud Run and Cloud SQL PostgreSQL, using deployment branch `main`.
- [ ] Approve Google Cloud project, budget, region, availability, public test access and service ownership.
- [ ] Create a separate hosted test database with authenticated encrypted connectivity and new Secret Manager credentials; block direct public database access and preserve local databases.
- [ ] Apply/verify hosted API port/probes, SQL attachment, secrets/runtime identity, persistent storage, backups and logs.
- [ ] Deploy an approved SHA/image over HTTPS; record runtime, region, release procedure and restrictions.
- [x] Retain the first complete hosted HTTP run: 156 passed / 1 failed, with target-specific HTTP and JUnit evidence.
- [ ] Rerun hosted acceptance after the approved fix and retain cloud revision/image and normal-restart evidence.
- [ ] Review representative AC-03 errors with a teammate and record the human review.
- [ ] Coordinate reset permission and run full suites in both directions with Team 6; record counts, failure owners and coverage limits.
- [ ] Update the class registry with service and test-runner locations, then finish the Q1-Q9 report and rendered models.

## Technical sources actually used

- FastAPI: https://fastapi.tiangolo.com/advanced/events/ and https://fastapi.tiangolo.com/how-to/extending-openapi/
- Psycopg transaction/connection contexts: https://www.psycopg.org/docs/connection.html
- CycloneDX library/packaged validators: https://github.com/CycloneDX/cyclonedx-python-lib
- PostgreSQL: https://www.postgresql.org/docs/16/
- Docker Compose health/dependency behavior: https://docs.docker.com/compose/how-tos/startup-order/
- OpenAPI 3.1: https://spec.openapis.org/oas/v3.1.0

Course sources are the Phase 2 report/instructions and Phase 3 assignment PDFs in
this directory. This document makes no new legal interpretation of the CRA.
