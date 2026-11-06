# Server coverage and proposed measures

November 6, 2026 publication review. **Team 2 proposed definitions; not confirmed
staff denominators, field names, or a promise of a particular grade.**

## Collection in the deployed grading profile

The system's explicit Docker `grading` target starts
`python -m autograder.grading_server`, with coverage.py 7.17.2 collecting before
application imports or worker-thread creation. Normal `production` images keep
the existing uvicorn entrypoint without the coverage dependency. Both system and
tester enable `AUTOGRADER_COVERAGE_ENABLED` and configure exact measurement
origins plus a shared Secret Manager key. See [deployment configuration](autograder-coverage-deployment.md).

For either role, ordinary POST `/test/run` acquires the existing shared execution
lock, marks its durable session running, and begins an authenticated measurement
window on the explicitly approved target. The window has a unique run nonce,
instance ID, role/session binding, deadline, and separate random request token.
The child receives only this short-lived request token, never the shared service
key or database credentials. The existing transport guard adds test/run headers
to **every** child Session, including raw concurrent requests, only after target
origin/path validation. Normal CLI traffic is unchanged.

The instrumented system serializes measured requests so global tracer contexts
cannot mix across asyncio/sync workers. Untagged traffic uses an excluded context;
stale/wrong-instance tokens return 409 before domain execution. Parent
`/test/run` and authenticated coverage controls bypass this lock so child requests
and finish calls cannot deadlock. One worker and one replica with concurrency
greater than one are required. A recovered abandoned parent releases its old
window using the shared report record; abort/timeout invalidates old nonces.

Before `/test/run` returns, the server exports a snapshot for that exact run and
combines it with actual JUnit outcomes. The result and compressed trace are saved
in the existing PostgreSQL session JSON. No shutdown flush, mounted volume,
Docker-exec importer, background CPU or separate coverage service is required.
The earlier local-only controller was retired; its historical artifacts remain
under ignored `artifacts/coverage/`.

Snapshots use an independent dataset so reporting cannot change the live
collector's query filter. File-level statement/branch statistics come directly
from coverage.py. Physical trace context lines are mapped to their preceding
logical executable statement for multiline conditions/calls; real coverage.py
tests verify this translation and branch isolation. Original physical contexts
are preserved. Redundant function/class region sections are omitted before
adding file-level contexts once, avoiding hundreds of MB of repeated data.
Any counted statement without a matching collected-test context is rejected.
Incomplete attribution yields an error report retaining the genuine test results.

The persisted gzip+base64 trace includes a SHA256, collector version, exact
server/test/collector source hashes, definition hash/version, UTC interval and
run/session/role/instance provenance. Secrets and coverage request tokens are not
in these artifacts or diagnostic logs. Historical reports remain unchanged.

## Code denominator

Every executable statement identified by coverage.py in these six domain modules:
`main.py`, `sbom_validation.py`, `timestamps.py`, `phase4.py`,
`purl_matching.py`, `osv_source.py`.

Statement coverage = executed logical statements / executable statements. Branch
coverage is separate: executed branch destinations / branch destinations. The
denominator includes zero-hit files and import/definition statements; execution
from startup/health/unattributed traffic is excluded. Tests, harness, SQL,
third-party packages, vendored schemas and CLI code are excluded. This is domain
Python coverage, not whole-stack coverage. Test pass rate is not used.

## Component denominator

Ten architectural responsibilities in [coverage-model.json](coverage-model.json),
derived from [the existing architecture/models](models.md):

| ID | Responsibility |
| --- | --- |
| C01 | Release registration/query |
| C02 | UTC support clock and timestamp normalization |
| C03 | CycloneDX structural validation |
| C04 | Inventory replacement/query |
| C05 | Transactional storage/reset |
| C06 | Fixture vulnerability source and package matching |
| C07 | Incident/submission persistence |
| C08 | Deadline derivation |
| C09 | OSV snapshot reading/range matching |
| C10 | OSV validation/atomic import |

A component counts only when an attributed statement executes inside one of its
listed function bodies. The report maps it to actual test IDs. Imports, endpoint
calls, selected names and passing tests alone do not count. Coverage is exercised
components / 10, a binary execution metric, not all internal branches or correctness.

## System-model denominator

Eighteen selected domain transitions, with exact behavioral test selectors,
parameter filters and required component witnesses in the machine-readable mapping:

- M01–M07: register; duplicate conflict preserving the original; UTC support
  expiry; initial SBOM ingestion; nested replacement; rejected invalid replacement
  preserving inventory; reset removing releases/inventory.
- M08–M15: mandatory incident initialization; early warning pending→met;
  notification pending→overdue; final N/A→scheduled on a fix; final scheduled→met
  independently; late submission remaining overdue; duplicate preserving its
  original; voluntary stages remaining N/A with rejected submissions.
- M16: fixture source available→outage→recovered with new matching records.
- M17: insertion failure→rollback preserving inventory.
- M18: absent OSV snapshot→validated, atomically activated generation.

A transition counts only if its named test passes the state assertions and server
traces from that same test execute every required component. Several transitions
can share one sequence; the numerator counts distinct transitions, not passing
tests or endpoints. Failed/skipped/missing assertions cannot certify transitions.
M17/M18 stay in the denominator without HTTP-suite witnesses: separate fault/
OSV runtime scripts do not become coverage for this run. Phase 5, startup, health
and harness lifecycle are outside this proposed domain model.

## Verification and limits

The request-driven Docker profile uses the intended grading image/entrypoint,
separate system/tester containers, 1 CPU/1 GiB, no bind mounts and no import step.
Tests check 201 responses/OpenAPI, 200 run/report, 353 passing cases per role,
immediate measured reports, compressed trace hashes, every counted statement's
context, consecutive-session isolation and cached retry. Runtime checks verify
measured report survival across domain reset/restart, hard interruption recovery,
subprocess timeout cleanup and reset refusal for an unapproved database.

Current fixture-suite evidence per role: **245/796 statements (30.78%)**, **75/240
branches (31.25%)**, **8/10 components (80%)**, **16/18 model transitions (88.89%)**.
C09/C10 and M17/M18 remain unexercised. Ordinary uninstrumented HTTP tests also
run separately: the serialized measurement run does not prove real concurrency.
See `artifacts/grading-live/` and [review handoff](autograder-fix.md) for results.

This verifies the deployed execution design locally, not an executed Cloud Run
rollout. Actual Cloud Run traffic, IAM/secret bindings, single-replica routing
and hosted measurements remain rollout gates. Tracer context history lives in
instance memory until it stops; monitor memory during extended grading windows.
An evicted or misrouted collector fails closed rather than mixing runs.

Peer origins without explicitly configured instrumentation remain unavailable.
No extension calls or service keys are sent to them. The grader's rejected fields,
cross-role session protocol and scorable coverage schema remain unknown. Tester
setup still selects its target; it does not fabricate a system-role session.

References: [coverage contexts](https://coverage.readthedocs.io/en/latest/contexts.html),
[Coverage API](https://coverage.readthedocs.io/en/latest/api_coverage.html).
