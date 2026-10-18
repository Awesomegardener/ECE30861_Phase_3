# Phase 3 status

No hosted availability, pod approval beyond the fixture README, or external CI
result is implied by code presence. Actual local runs are in `testing.md`.

The updated local service is healthy on port 8080. Its original PostgreSQL volume
and row fingerprints are unchanged; port 18080 is a separate test stack. The
final local suite passed 67 tests. This is local operational evidence, not a
network-accessible hosted deployment or completed Phase 3 submission.

## Acceptance mapping

| AC | Main automated checks | Current evidence |
|---|---|---|
| AC-01 / REQ-01 | `test_ac01_shared_release_cases`, `test_ac01_support_boundary`, `test_release_invalid_types_save_nothing` | Shared requests, rejection without a row, UTC boundary and rollover pass locally |
| AC-02 / REQ-02 | `test_ac02_shared_25_components_are_isolated` | Exact 25-name/version/purl inventory under the first release and zero under the second pass locally |
| AC-03 / REQ-02 | `test_ac03_invalid_sbom_never_changes_inventory`, `test_ac03_unknown_release_stores_nothing` | Malformed JSON, missing mandatory fields, plaintext and unknown release pass; populated inventory preservation also checked |

Oracles come from unchanged shared release expectations, the SBOM's own component
tuples, the matching source lock file and OpenAPI schemas/statuses. No live CVE
service or AI-generated expected inventory is used. Error reasons have explicit
automated assertions and remain available in response artifacts for human review.

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

## Limitations and remaining delivery work

| ID | Severity | Limitation / workaround | Next action |
|---|---|---|---|
| LIM-01 | High | Nested inventory children are validated but not stored. Use the agreed flat fixture for current cross-tests. | Resolve normalization/counting with pod before claiming Phase 3 complete |
| LIM-02 | Medium | Missing component version/array and supported-version policies are not fully specified. Existing rejection behavior remains. | Pod decision and matching tests |
| LIM-03 | Medium | Product/version nonempty prose conflicts with YAML; timestamp/error/reset details are incomplete. | Reconcile documents without unilateral API changes |
| LIM-04 | High for delivery | No verified network host, registry entry or cross-team execution. Local Docker evidence only. | Obtain hosting approval, deploy, record SHA/platform/availability and update registry |
| LIM-05 | Medium | CI workflow is local source; no hosted run or branch-protection evidence. | Approved push, obtain CI URL, configure required checks if authorized |

Phase 4 remains REQ-03–06 / AC-04–07, including vulnerability fixture control.
Phase 5 remains REQ-07–08 / AC-08–10. The Phase 3 parsing and delivery gaps above
must not be silently deferred as a shared-scope reduction. Dependency-Track
performance/failure behavior remains an investigation before Phase 4.

Before submission: record both cross-team directions, counts, coverage limits,
failure owners, and one actual specification disagreement/resolution plan; include
deployed logs/version evidence and the web-service/test-runner registry locations.
Each teammate must supply their own factual GenAI-use and verification account.
No teammate activity, hosting result, or pod decision has been invented here.

## Technical sources actually used

- FastAPI: https://fastapi.tiangolo.com/advanced/events/ and https://fastapi.tiangolo.com/how-to/extending-openapi/
- Psycopg transaction/connection contexts: https://www.psycopg.org/docs/connection.html
- CycloneDX library/packaged validators: https://github.com/CycloneDX/cyclonedx-python-lib
- PostgreSQL: https://www.postgresql.org/docs/16/
- Docker Compose health/dependency behavior: https://docs.docker.com/compose/how-tos/startup-order/
- OpenAPI 3.1: https://spec.openapis.org/oas/v3.1.0

Course sources are the Phase 2 report/instructions and Phase 3 assignment PDFs in
this directory. This document makes no new legal interpretation of the CRA.
