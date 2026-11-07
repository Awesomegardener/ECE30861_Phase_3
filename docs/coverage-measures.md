# Coverage under the supplied cross-team interface

The full [Cross-team Testing Interface v0.4.2 prose](https://docs.google.com/document/d/1GhEVTw3a2tNJY2arfDyWgWS94kVYfgC7/edit) defines the three `covered`, `total`, `basis` entries. Counts describe exercise, independently of correctness. Unavailable measurements use **null/null**, with a reason, never substituted zero percentages. The earlier ten-component/eighteen-transition proposal is retired: model transitions are not the requested system coverage.

## Code: actual target execution

The system Docker `grading` target runs `python -m autograder.grading_server`. Coverage.py starts **before application imports and worker creation**, measuring executable statements in six domain files: `main.py`, `sbom_validation.py`, `timestamps.py`, `phase4.py`, `purl_matching.py`, `osv_source.py`. The denominator includes zero-hit files and definition/import statements; tests, harness, SQL, third-party code, vendor schemas and CLI code are excluded. This is domain Python statement coverage, not whole-stack or test-runner coverage.

With `AUTOGRADER_COVERAGE_ENABLED=true`, successful system setup starts a new random tracer context tied to the supplied session ID. Project requests since setup execute in that context. Startup, setup/report, health and test-adapter execution are excluded. Project `/api/v1/test/*` controls are still project requests and count any domain statements they execute. A request lock serializes domain dispatch and context changes so asynchronous and worker-thread execution cannot mix contexts; the suite's intentional concurrent writes are additionally tested without instrumentation in ordinary CI.

`GET /test/report` snapshots the live collector into an independent stopped dataset before querying contexts. This avoids altering the live collector's filters. It returns actual executed/executable source statements and source hashes, not percentages inferred from HTTP results. No private coverage endpoint, shared service secret, shutdown flush, persistent filesystem, Docker importer or background job is required. The tester retrieves this ordinary system report by the same ID after its project requests and persists the returned measure with its immutable suite report.

The active collector is in process memory, requiring one worker/replica and request concurrency >=2 in the intended deployment. Before a new setup replaces the global test baseline, the old context's measure is frozen in PostgreSQL. Old-session requests bearing our optional session header are refused before execution. Subsequent sessions get fresh contexts even if they execute the same lines. Repeated report reads do not change counts; later project calls can increase current-session counts. Terminal tester reports are not recalculated. A lost/restarted/uninstrumented collector yields null/null with a reason; it never imports another session's counts. Frozen system measures and final tester reports persist in the report database across restarts.

The ordinary `production` image does not enable source instrumentation. Build the `grading` target and enable it on the **system** for measured reports; enabling tester-only env flags cannot measure a remote service. A peer system can implement its own collector and return the contract fields; our tester validates the ID, counts and basis without assuming our provenance extensions.

## Component: unavailable without pod definitions

The [pod Phase 2 specification](https://docs.google.com/document/d/1jRBiYWWyYGn-SjoQ4pHxduenk8bkCmpJAyVD0Wt8SP8/edit) Q2 describes capabilities and Q7 discusses architectural implementation choices, including Dependency-Track versus a local matcher and optional workflow services. It does **not** establish a shared component list/denominator or exercise rules. Implementation-specific functions, OSV responsibilities, SBOM inventory items and endpoint counts cannot substitute for that missing pod definition. The component entry therefore reports null/null and explains the gap. Agreeing and documenting that definition within the pod is the remaining requirement for a numeric component measure; no staff guess is used.

## System: pod acceptance criteria

The denominator is the **ten acceptance criteria AC-01–AC-10 in pod Q4.1**. The current suite exercises the automated scenarios for AC-01–AC-07 and contains no AC-08/09/10 report-schema/audit/restart scenarios. Those three remain in the denominator as uncovered. Human review portions of AC-03/06 are not claimed as completed.

The pod gives concrete scenario inputs and evaluation rules, but does not separately formalize a coverage predicate. Our implementation explicitly interprets **exercise** as dispatch of all mapped scenario inputs below, regardless of response status or whether assertions pass. This is our stated measurement rule based on the pod's scenarios, not a separately instructor-approved predicate. Missing dispatches leave a criterion uncovered. A failed assertion or failed transport may prevent later inputs and thus reduce exercise, but passing tests alone never increase coverage. Both failed and passing responses to the same dispatched scenarios count equally.

| Criterion | Required scenario dispatch witnesses |
| --- | --- |
| AC-01 | Four release registrations (past/current/future/missing end date), three support-boundary reads |
| AC-02 | Shared 25-component SBOM upload and three inventory reads covering the original and isolated second release |
| AC-03 | Malformed JSON, missing CycloneDX fields, plaintext, and valid SBOM against unknown release |
| AC-04 | Five seeded CVE queries covering the shared precision/recall/support grouping scenario |
| AC-05 | Known-unaffected, unknown and unavailable-source CVE queries |
| AC-06 | Mandatory/voluntary creation and reads, invalid rationale/classification submissions |
| AC-07 | Fixed-clock mandatory incident creation/read, exact-boundary early warning, fix update and final submission |
| AC-08–10 | No mapped suite scenario; uncovered |

`autograder.coverage.acceptance_coverage` maps canonical test identities and HTTP method/path dispatches to these witnesses. It uses the complete per-run HTTP evidence before temporary files are removed. Coverage contains the distinct exercised criteria and scope in `basis`; it is neither endpoint coverage nor pass rate. An aborted suite without a complete evidence bundle reports the system measure unavailable, retaining all journaled test outcomes.

## Verification and limits

Contract tests include malformed requests, failure envelopes, readiness, one-run rules, upstream setup errors and immutable report lookup. Isolated HTTP tests execute the real 353-case suite against both an internal target address and the exact rejected HTTPS `target_url`, then retrieve both reports. A direct system-only test observes zero covered statements before project calls, actual growth after a request, stable reads, frozen prior-session counts, and zero fresh-session counts. A short-budget tester verifies partial results, error/skip classifications and repeated-run rejection after abort.

These checks establish the deployed **execution design locally** using the intended grading entrypoint. They do not establish that public Cloud Run revisions have been updated. No public deployment/reset is performed by this change. Registered URLs/access notes and independent peer cross-team runs remain operational checks, separate from local contract conformance.
