# Phase 3 implementation decisions and open pod questions

The shared `openapi.yaml` and `fixtures/` are unchanged. Items marked pending
are discussion points, not new pod agreements.

| Topic | Current implementation / evidence | Status |
|---|---|---|
| Shared fixtures | `fixtures/README.md` records Team 2 agreement on 2026-10-17. This file does not supply additional approval evidence. | Reported agreement |
| Empty product/version | OpenAPI permits empty strings; Phase 2 section 5.2 says nonempty. Preserve the OpenAPI behavior until the pod aligns these sources. No automatic whitespace trimming. | Pending pod agreement |
| Date input | Enforce the contract's string/date representation, YYYY-MM-DD; reject numeric timestamps and date-time values. | Contract implementation |
| User attribution | Enforce `X-User-Id` minimum length 1 on application mutations. Test controls have no header requirement. | Contract implementation |
| Clock input/output | Preserve offset input permitted by OpenAPI; normalize calculations and output to UTC with `Z`. Reject timezone-free or numeric values. Existing invalid-input status remains 400. Whether inputs must literally end in `Z`, and documenting clock errors in OpenAPI, remain open. | Pending contract clarification |
| Reset defaults | Preserve existing behavior: clear implemented application state and remove the clock override, reverting to real UTC. Exact shared default clock and future vulnerability fixtures are unspecified. | Pending pod agreement |
| Error codes | Preserve existing Phase 3 codes, including fixture expectation `INVALID_REQUEST`. OpenAPI only constrains the error envelope. Exact cross-team constants need confirmation. | Pending pod agreement |
| CycloneDX versions | Validate using packaged official schemas rather than retrieving request-supplied `$schema` URLs. The shared fixture establishes a required 1.6 success case, not an exclusive version range. | Supported range needs pod confirmation |
| Missing component version / components array | Preserve current rejection until the valid-CycloneDX input requirement is reconciled with required output version strings and empty inventory semantics. | Pending pod agreement |
| Nested inventory | Full schema validation must include nested content. Inventory flattening/counting and inclusion of metadata component children are not yet agreed. Preserve top-level normalization and disclose this limitation. Never count tools or the metadata root as inventory. | Pending pod agreement; Phase 3 risk remains |
| No-write verification | A valid retry of the rejected product/version must return 201. Audit assertions belong to the later audit increment. | Phase 3 test approach |

The Phase 3 rubric also says test-runner instructions are unnecessary in Q4.1,
while the delivery overview requires a runner location/instructions. Supply them
and ask the instructor if any further artifact is expected. Shared scope reductions
require both teams' agreement and instructor sign-off; no scope reduction is made.
