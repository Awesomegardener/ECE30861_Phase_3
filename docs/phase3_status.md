# Phase 3 status

Committed baseline `0c067d85d7977a32409fa3f552a225424a0b83c1` on `main` has a
[successful GitHub Actions run](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39087275607),
confirmed on 2026-10-18. That run verifies the baseline. CI for the commit
introducing the policy/normalization changes must be checked separately.
No public hosted availability or
cross-team execution is implied by either CI or local tests.

The current supplied-policy increment passed **264 local tests**, comprising
157 HTTP checks against a newly built Docker API/PostgreSQL stack and 107 local
tests (51 SBOM, 42 clock, 10 evidence, 4 startup). The isolated project is
`cra-phase3-pod-decisions-20261018`, port 18082. Its report evidence contains
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

## Limitations and remaining delivery work

| ID | Severity | Limitation / workaround | Next action |
|---|---|---|---|
| LIM-01 | Medium for cross-team readiness | Recursive inventory is implemented/tested. Metadata/tool exclusion and occurrence retention are still Team 2 proposals, without supplied Team 6 acknowledgement. Identical sibling duplicates remain schema-invalid. | Obtain acknowledgement and record the schema-valid duplicate boundary; do not weaken CycloneDX validation |
| LIM-02 | Medium | Version range and required descendant versions follow the supplied Team 2 acceptance. Metadata-only/absent-array input policy is still unspecified; existing behavior is retained. Old top-level records cannot recover omitted children without the original SBOM. | Retain final shared policy record; clarify absent-array behavior; coordinate any resubmission without resetting existing data |
| LIM-03 | Medium | Product/version nonempty prose conflicts with YAML; timestamp/error/reset details are incomplete. | Reconcile documents without unilateral API changes |
| LIM-04 | High for delivery | No verified network host, registry entry or cross-team execution. Local Docker and hosted CI evidence only. | Obtain hosting approval, deploy, record SHA/platform/availability and update registry |
| LIM-05 | Medium | Baseline `0c067d8` has verified successful main CI. The policy increment has local verification recorded below; check CI for its released SHA separately. Branches were reported unprotected during earlier review; that setting was not rechecked or changed here. | Retain CI evidence for the new released SHA; user has authorized saving the reviewed increment to main |
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
- [x] Retain successful main CI URL for committed baseline `0c067d8`.
- [x] Obtain teammate review and user authorization to commit/push this increment to `main`.
- [ ] Verify the increment's own CI run for its released SHA.
- [x] Select Google Cloud Run and Cloud SQL PostgreSQL, using deployment branch `main`.
- [ ] Approve Google Cloud project, budget, region, availability and service ownership, plus proposed startup/health changes.
- [ ] Create a separate hosted test database with authenticated encrypted connectivity and new Secret Manager credentials; block direct public database access and preserve local databases.
- [ ] Configure the API port, database-aware readiness, persistent storage, backups/recovery and timestamped logs.
- [ ] Deploy an approved SHA/image over HTTPS; record runtime, region, release procedure and restrictions.
- [ ] Run the complete HTTP suite against that hosted test service and retain target-specific evidence, JUnit results and normal-restart snapshots.
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
