# Phase 3 status

Commit `2a95313d524e07072bead8eff0b6ea3035e2ecf8` on `phase3-improvements` passed
[GitHub Actions](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39082032962):
67 tests, static checks, Docker startup and the SQL rollback check. The run
completed on 2026-10-18 UTC. No public hosted availability or cross-team execution
is implied by this CI result.

The subsequent clock/evidence increment passed 153 local tests
(100 HTTP and 53 local tests) against a fresh Docker test project on port 18081.
Its report bundle contains 519 HTTP exchanges with timestamps, target/version
provenance, and captured bodies. The original application on port 8080 and prior
test stack on port 18080 were not refreshed or reset. Actual results and data
preservation evidence are in `testing.md`. Hosted CI verification must be checked
against the increment's own commit/run; the linked initial run only covers `2a95313`.

## Acceptance mapping

| AC | Main automated checks | Current evidence |
|---|---|---|
| AC-01 / REQ-01 | `test_ac01_shared_release_cases`, `test_ac01_support_boundary`, `test_release_invalid_types_save_nothing` | Shared requests, rejection without a row, UTC boundary and rollover pass locally |
| AC-02 / REQ-02 | `test_ac02_shared_25_components_are_isolated` | Exact 25-name/version/purl inventory under the first release and zero under the second pass locally |
| AC-03 / REQ-02 | `test_ac03_invalid_sbom_never_changes_inventory`, `test_ac03_unknown_release_stores_nothing` | Malformed JSON, missing mandatory fields, plaintext and unknown release pass; populated inventory preservation also checked |

Oracles come from unchanged shared release expectations, the SBOM's own component
tuples, the matching source lock file and OpenAPI schemas/statuses. No live CVE
service or AI-generated expected inventory is used. Error reasons have explicit
automated assertions and are now retained in opt-in HTTP response artifacts for
human review. Capturing those artifacts does not constitute completed human review.

## Every shared operation

Paths have prefix `/api/v1`. “Observed” means local checks, not universal conformance.

| Operation | Requirement / phase | Implementation | Success / errors |
|---|---|---|---|
| POST /releases | REQ-01, future REQ-08 | Partial overall | 201/400/409 observed; audit absent; empty-string policy open |
| GET /releases/{releaseId} | REQ-01 | Implemented | 200/404 observed; UTC boundary checked |
| PUT /releases/{releaseId}/sbom | REQ-02, future REQ-08 | Partial overall | 200/400/404 observed; nested normalization and version policies open; audit absent |
| GET /releases/{releaseId}/components | REQ-02 | Partial overall | 200/404 observed; complete shared flat fixture; nested inventory incomplete |
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
| LIM-01 | High | Nested inventory children are validated but not stored. Use the agreed flat fixture for current cross-tests. | Resolve normalization/counting with pod before claiming Phase 3 complete |
| LIM-02 | Medium | Missing component version/array and supported-version policies are not fully specified. Existing rejection behavior remains. | Pod decision and matching tests |
| LIM-03 | Medium | Product/version nonempty prose conflicts with YAML; timestamp/error/reset details are incomplete. | Reconcile documents without unilateral API changes |
| LIM-04 | High for delivery | No verified network host, registry entry or cross-team execution. Local Docker and hosted CI evidence only. | Obtain hosting approval, deploy, record SHA/platform/availability and update registry |
| LIM-05 | Medium | Initial commit has a verified CI pass; the clock/evidence increment has recorded local verification and needs its own hosted CI evidence. Branches were reported unprotected during review. | Retain the CI URL/results for the released SHA; configure required checks only if authorized |
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

- [ ] Agree on nested-component normalization and remaining input/reset policies with Team 6.
- [ ] Retain the new CI URL and artifacts for the released clock/evidence commit.
- [ ] Select and approve hosting, budget, region, availability and service ownership.
- [ ] Create a separate hosted test database with private connectivity and new environment-managed credentials; preserve local databases.
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
