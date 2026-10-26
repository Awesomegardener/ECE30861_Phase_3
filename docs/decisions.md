# Phase 3 implementation decisions and open pod questions

The shared `openapi.yaml` and `fixtures/` are unchanged. Contract version remains
1.0.0. Implementation authorization and mutual pod approval are separate facts.

## Evidence and approval status (2026-10-18)

- The shared OpenAPI and Phase 2 report are the authoritative existing agreement.
  `fixtures/README.md` records Team 6 creation/review and Team 2 sign-off on
  2026-10-17; those shared files have not been edited.
- The user supplied Team 6's six questions and Team 2's written responses in the
  implementation request on 2026-10-18. Team 2 explicitly says "Agree" to items
  1-5. Item 6 is a recommendation. This is evidence of those supplied positions,
  not independent verification of authorship or a final Team 6 approval record.
- The user authorized compatible implementation now. Metadata/tool exclusion,
  retaining repeated occurrences, and the broader exact-code testing policy
  remain Team 2 proposals until Team 6 acknowledges them. Their implementation
  here must not be described as a completed pod-wide contract revision.
- The user subsequently reported teammate review/approval of the implementation
  and explicitly authorized committing and pushing it directly to `main`.
  This records implementation/release approval, not additional Team 6 approval
  of the outstanding shared-contract proposals.

## Supplied decisions compared with the existing interface

| Item | Before this increment | Contract / Phase 2 comparison | Result and agreement status |
|---|---|---|---|
| 1. Missing `X-User-Id` | Both implemented application mutations already returned 400 `INVALID_REQUEST`; test controls were exempt. | Shared `UserId` is required and has `minLength: 1`; Phase 2 section 5 requires attribution. Error constants are not enumerated in YAML. | Retained behavior. Exact missing-header code now tested on POST releases and PUT SBOM. Team 2 accepted Team 6's stated proposal in the supplied exchange. |
| 2. CycloneDX versions | Accepted packaged JSON schema versions 1.2-1.7. | OpenAPI says valid CycloneDX JSON but does not enumerate versions. The shared fixture and Phase 2 example use 1.6; they do not establish an exclusive range. | Restrict to 1.4, 1.5, 1.6 and explain unsupported-version 400 errors. This is the supplied support-policy clarification accepted by Team 2, not an enum added to the shared contract. Obtain the final shared decision record. |
| 3. Required inventory versions | Missing versions were checked only at the top level. | Public `Component` requires string `name` and `version`. CycloneDX alone can allow a missing version, so API normalization needs this additional rule. | Reject the entire request when any inventory descendant lacks a string version; no writes. Team 2 accepted the supplied proposal. Do not invent a version or a new nonempty-string rule. |
| 4. Release lookup first | Already checked the release before content type, JSON parsing or schema validation. | Shared 400/404 responses and registered-release prerequisite support this behavior; simultaneous-error precedence is not specified in YAML. | Retained behavior and added 18 invalid-body precedence cases. Tests supply the required header. Team 2 accepted the supplied proposal. |
| 5. Nested inventory | Validated descendants but stored top-level components only. | REQ-02 stores release components; Phase 2 section 6.1 explicitly identifies nested normalization as Phase 3 risk. The public inventory/count shapes support flattening but do not define scope or duplicate handling. | Traverse root `components` and their `components` descendants at every depth. Store/count every occurrence. Exclude the entire metadata component/tool subtrees. Team 2 accepted flattening; exclusion and multiplicity are Team 2 proposals awaiting Team 6 acknowledgement. |
| 6. Error assertions | Most HTTP tests checked status/envelope/reason; clock tests imposed the local exact code. | Shared `Error` requires string code/message but generally does not fix code constants. The shared release fixture explicitly expects `INVALID_REQUEST` for missing support date. | Require meaningful nonempty messages for errors. Assert exact missing-header `INVALID_REQUEST` and existing shared-fixture expectations; otherwise check status, envelope and reason without prescribing local constants. Team 2 recommendation; broader mapping still pending. |

## Duplicate-policy boundary requiring pod acknowledgement

Retaining occurrences does not override valid-CycloneDX validation. Official
1.4-1.6 schemas require unique items within each `components` array. Identical
sibling JSON objects therefore still return 400, at root or nested levels.
Schema-valid repeated name/version/purl tuples (for example with distinct
`bom-ref` values), and identical versioned objects in separate parent arrays,
are retained as separate inventory rows. Tests cover both cases.

If "retain duplicates" is intended to accept identical siblings that violate
the schema, that conflicts with the shared contract's valid-CycloneDX requirement
and needs explicit pod/instructor reconciliation before changing validation.
No such relaxation has been implemented. Do not reuse `bom-ref` values when the
CycloneDX specification requires them to be unique within a document.

Sources: [official 1.4 schema](https://github.com/CycloneDX/specification/blob/master/schema/bom-1.4.schema.json),
[official 1.5 schema](https://github.com/CycloneDX/specification/blob/master/schema/bom-1.5.schema.json),
and the packaged official 1.6 schema used by the strict validator.

## Other policies and remaining questions

| Topic | Current implementation / evidence | Status |
|---|---|---|
| Shared fixtures | `fixtures/README.md` records Team 2 agreement on 2026-10-17. This file does not supply additional approval evidence. | Reported agreement |
| Empty product/version | OpenAPI permits empty strings; Phase 2 section 5.2 says nonempty. Preserve the OpenAPI behavior until the pod aligns these sources. No automatic whitespace trimming. | Pending pod agreement |
| Date input | Enforce the contract's string/date representation, YYYY-MM-DD; reject numeric timestamps and date-time values. | Contract implementation |
| User attribution | Enforce `X-User-Id` minimum length 1 on application mutations. Missing-header exact code is covered above; no Phase 4 PATCH route is added. Test controls have no header requirement. | Contract implementation plus supplied clarification |
| Clock input/output | Enforce RFC 3339 syntax before existing aware-date/calendar validation. Preserve numeric offsets, fractional seconds, and lowercase `t`/`z`; normalize calculations/output to UTC with `Z`. Reject numeric strings, timezone-free values, invalid separators and malformed offsets. Existing invalid-input status remains 400. Whether inputs must literally end in `Z`, and documenting clock errors in OpenAPI, remain open. | Syntax defect fixed; policy clarification remains pending |
| Reset defaults | Preserve existing behavior: clear implemented application state and remove the clock override, reverting to real UTC. Exact shared default clock and future vulnerability fixtures are unspecified. | Pending pod agreement |
| Error codes | Preserve local `INVALID_JSON`, `INVALID_SBOM`, `NOT_FOUND`, `CONFLICT`, and `DATABASE_ERROR` behavior without treating all constants as shared mappings. Internal SQL-fault tests may check our own database error code. | Broader exact-code table pending |
| Components array | Preserve existing rejection of an absent/non-array `components`; explicit empty array is accepted. Metadata-only/absent-array behavior is not settled by the supplied exchange. | Pending pod clarification; behavior unchanged |
| Multiple simultaneous errors | Required-header validation still occurs before the handler's release lookup. Unknown-release 404 precedence is established only with a valid required header. | Header-vs-release precedence needs explicit cross-team policy if tested |
| Retrieval ordering / hierarchy | Flat API stores name/version/purl occurrences, not parent relationships. No output ordering is promised. Old top-level-only records cannot acquire omitted descendants without resubmitting the original SBOM, which is not stored. | No schema migration or existing-data rewrite in this increment |
| No-write verification | A valid retry of the rejected product/version must return 201. Audit assertions belong to the later audit increment. | Phase 3 test approach |

The Phase 3 rubric also says test-runner instructions are unnecessary in Q4.1,
while the delivery overview requires a runner location/instructions. Supply them
and ask the instructor if any further artifact is expected. Shared scope reductions
require both teams' agreement and instructor sign-off; no scope reduction is made.

## October 26 HTTP autograder extension (provisional compatibility)

Staff's supplied announcement identifies separate system/tester base URLs and
appended `/test*` paths but does not supply complete payloads/status/lifecycle
rules. The user authorized independent implementation using Team 6's **published
documentation**, pinned at `9c0b1917b6ed316d51b412685805bd8766b8edea`, as a
provisional external-interface reference. No peer code/test/database design was
consulted or copied; no staff approval of this extension is claimed.

We implement both roles, synchronous pytest runs, durable session reports and a
shared PostgreSQL execution lock. Our 157 tests and all existing CRA behavior
remain unchanged, including recursive nested inventories. The timeout, allowlist,
immutable sessions, duplicate-ID 409, configuration 503 and interruption recovery
choices are documented in `autograder-interface.md` and the separate
`autograder-openapi.yaml`. They are Team 2 extension policies, not amendments to
the original shared `openapi.yaml`. The harness's test-result reports do not
implement Phase 5 regulatory report functionality.

Confirm staff acceptance of the provisional request/report schemas, latest-session
defaults and synchronous duration (our historical hosted run was about 104 seconds,
not Team 6's few seconds). Coordinate exclusive destructive-test windows with
Team 6: their independent tester does not share our execution lock. Metadata
persistence uses a database on the existing Cloud SQL instance; the retained
application database is never a default local test target.

Final safety implementation: system role self-tests are restricted to
`http://127.0.0.1:PORT`, and adapter resets require the dedicated `cra_grading`
database in both configuration and the live connection. Harness-only pytest
transport rejects alternate origins/API paths, disables redirects and ignores
environment proxies; original portable tests/fixtures remain unchanged. Before
running against our known public URL, the tester requires our system discovery
to return `role: system, reset_ready: true`, so an old course revision cannot be
tested before its grading-database migration. That field is an optional Team 2
extension, not a new Team 6 or staff requirement. The deployment guide specifies
ordinary SQL roles, separate database/schema grants and migration/traffic order.
