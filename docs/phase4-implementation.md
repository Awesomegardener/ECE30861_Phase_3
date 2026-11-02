# Phase 4 implementation

November 1, 2026. Local changes on base `ad42a439b81fdfd42ab50e44cea4c53717d07769`;
not committed, remotely verified or deployed. See [current review](phase4-pod-update.md).

## Operations and shared contract

| Operation | Behavior |
|---|---|
| GET `/api/v1/vulnerabilities/{cveId}/affected-releases` | 200 grouped inventory; malformed400 INVALID_REQUEST; unknown404 CVE_UNKNOWN; source failure503 VULNERABILITY_SOURCE_UNREACHABLE |
| PUT `/api/v1/test/vulnerability-source` | Grading-only whole-list replacement; omitted records means empty; unsafe configuration503 |
| POST `/api/v1/incidents` | 201; optional format-only CVE; awareness, actor, classification, preserved nonempty rationale |
| GET `/api/v1/incidents/{incidentId}` | 200 persisted case and derived stages; unknown404 |
| PATCH `/api/v1/incidents/{incidentId}` | 200 replaces fix; chronology/format400; unknown404 |
| POST `/api/v1/incidents/{incidentId}/submissions` | 201; chronology/N/A400; duplicate409 CONFLICT; unknown404 |

Mutations require X-User-Id except test controls. Original shared `openapi.yaml`
remains unchanged. Additional errors/clarifications are in **unapproved**
`openapi.phase4-proposed.yaml`. Duplicate409 is authorized local behavior, not yet
an enumerated shared response. Source/test-control negative responses have the
same explicitly recorded distinction.

## Sources

Default OSV reads real schema-validated records/aliases/provenance from PostgreSQL.
Explicit versions, SEMVER and PyPI ECOSYSTEM ranges are supported. Unsupported
required comparisons fail503; HTTP lookup never downloads data. See [OSV operations](osv-snapshots.md)
and [ADR](adr-0001-osv-snapshots.md) for limits and the Dependency-Track deviation.

Fixture mode additionally requires test enablement and actual matching disposable
DB. It strips PURL qualifiers/subpaths and matches exact versions. Missing PURLs
cannot match. PUT replaces all records; reset sets available/empty and never erases
OSV generations. Non-grading databases refuse reset before truncation.

Both sources return stored component fields, retain occurrences, group releases
by UTC support date and read one repeatable-read snapshot. Ordering is not
contractual. [AC04 reviewer evidence](ac04-fixture-review.md) is prepared but has
no invented sign-off. Exact set equality and independent latency assertions remain.

## Incidents and deadlines

Timezone-aware RFC3339 accepts Z/numeric offsets including -00:00, keeps up to six
fractional digits and emits UTC Z. Naive/invalid/overflow timestamps return400.
Future timestamps are allowed; fix/submission before awareness returns400 without
mutation. A fix may be replaced; voluntary fixes persist with all stages N/A.

Mandatory deadlines are awareness+24h, awareness+72h and fix+14d. Final without fix
is N/A. Unsubmitted applicable stages stay pending at equality, overdue after;
submitted<=deadline is met, otherwise overdue even if clock moves backward.
Submissions to N/A return400. Incident row locking serializes stage duplicates:
one201 and one409 under concurrency. Old duplicate rows are preserved; earliest
submission is used for legacy reads. Latest actor/update time is not immutable
correction history. No push alerts, Phase5 reports or complete audit exist.

Startup adds incident/source/OSV schema under the existing transactional advisory
lock. Release/SBOM records remain intact; retained `cra_phase3` is refused before
DDL. No destructive dedup migration is performed. Reports and cooperating-runner
locks remain in separate `cra_autograder`. Direct test controls/independent CLI
runs still require exclusive coordination; the adapter lock cannot protect them.

## Test coverage

353 portable cases =157 original +196 Phase4: AC04=10, AC05=11, AC06=62, AC07=113.
Both adapters use real pytest/JUnit and require identities, groups and counts.
Original157 tests/conftest, shared contract and Team6 fixtures are byte-identical.
All154 previous Phase4 scenarios remain covered; their contradictory policy
expectations were updated under this request and42 further cases were added.
Negative mutation assertions still require unchanged state. OSV unit/runtime
checks are additional, separate from synthetic portable acceptance cases.

Local results are not hosted verification, full-feed coverage, operational refresh
or Team6 compatibility. See the paired deployment guide for same-SHA rollout,
0%-traffic shared-database caveat, safe permissions and rollback.
