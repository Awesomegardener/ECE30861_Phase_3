# Phase 4 Q6.1 cross-team results — fill from actual evidence

Status: **Pending both directions.** Do not substitute local353/353 results for
cross-team evidence. Follow [the run guide](phase4-cross-team-testing.md).

Suggested2–3-sentence narrative after execution:

> On [UTC date/window], Team2 ran [actual run count] cases against Team6's confirmed
> [URL/revision], and Team6 ran [actual count] cases against Team2's [URL/revision].
> Results were [actual passed/failed/errors/skipped for each direction]; the main
> mismatches were [issues and owners]. Coverage evidence is [links], with [code,
> component or model coverage unavailable] explicitly recorded as unavailable.

| Field | Team2 full suite → Team6 service | Team6 full suite → Team2 service |
|---|---|---|
| Status | Pending authorization and current URL | Pending reciprocal window and deployed readiness |
| Confirmed system URL | Previously http://136.116.160.182:8080; reconfirm | https://cra-phase3-api-456725640364.us-central1.run.app; reconfirm grading revision |
| Tester URL / runner SHA / image / revision | Pending | Pending; obtain from Team6 |
| Target deployed SHA / revision | Pending; obtain from Team6 | Pending; record actual deployed system SHA |
| Written reset approval, approver, permitted DB/scope | Pending | Pending |
| Exclusive window / started / finished (UTC) | Pending | Pending |
| Session ID / report URL / artifact links | Pending | Pending |
| Expected collected cases |353 (157 Phase3+196 Phase4) | Team6 must supply its full-suite count |
| Actual collected / report records | Pending | Pending |
| Passed / failed / errors / skipped | Pending | Pending |
| Overall result / HTTP status | Pending; HTTP200 alone is not pass | Pending |
| Main issues and accountable owner | Pending | Pending |
| What failed and how diagnosed | Pending | Pending |
| Fix / shared-spec issue / retest plan and date | Pending | Pending |
| Contract and fixture hashes / proposal version | Pending | Pending |
| Code coverage artifact / instrumented target version | Not yet available | Not yet available |
| Component coverage and missing components | Pending | Pending |
| System-model coverage and missing transitions | Pending | Pending |

Use one entry per actual failing check or clustered root cause:

| Test IDs / AC / endpoint | Expected / actual status and body | Severity / impact | Owner | Spec ambiguity or implementation defect | Resolution / retest |
|---|---|---|---|---|---|
| Pending | Pending | Pending | Pending | Pending | Pending |

Coverage must distinguish:

- **Black-box contract/AC evidence:** per-test outcomes, operation-status list,
  actual request/response examples, status codes and UTC times. Our suite spans
  AC01–07; Phase4 AC04=10, AC05=11, AC06=62, AC07=113. This is not source coverage.
- **Code coverage:** target-side instrumentation and its exact revision/measurement
  window. Team6 supplies coverage for our tests on their service; Team2 supplies
  coverage for their tests on ours. If unavailable, state that instead of inferring
  a percentage from passing tests. Do not instrument/change cloud resources now.
- **Component coverage:** map observed operations to release/SBOM validation,
  inventory matching/source errors, incident persistence and deadline calculation.
  Distinguish fixture-source coverage from real OSV-source coverage and list gaps.
- **System-model coverage:** map test IDs to states/transitions in `models.md`,
  such as unknown/known/affected/unavailable and pending/met/overdue/N/A. Include
  time boundaries, offset normalization and rejected transitions; list untested
  paths. No claimed percentage without a defined model denominator and evidence.

Attach both teams' permission/URL confirmation, full summary/checks/failures,
runner/target versions, UTC window, contract/fixture hashes and available coverage
artifacts. Reports contain bounded examples, not a complete downloadable JUnit or
server log. Obtain additional artifacts from each operator as needed. Record a
failed/incomplete attempt truthfully; never remove assertions to improve totals.
