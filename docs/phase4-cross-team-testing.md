# Phase 4 Q6.1: bidirectional cross-team testing

Prepared November 1, 2026. **No requests were sent to either deployed API during
this check. Team6 URL confirmation and reset permission are pending.**

## What is verified locally

The separate **tester** supports both exact target origins when explicitly
configured. The **system** adapter remains self-only at loopback; do not send it
a Team6 target or remove that restriction.

| Capability | Evidence / limit |
|---|---|
| POST tester `/test/setup` accepts an approved `target_base_url` | Nine new offline cases exercise real installed route handlers with in-memory storage. Both literal public URLs accepted; setup does not contact/reset them. |
| POST `/test/run` uses the selected session target | Offline checks capture the real Runner command before launching a child: both suite files, selected `--base-url`, selected `CRA_HARNESS_TARGET` and transport guard. Stored target is used even when default is Team2 and run specifies only session ID. |
| GET `/test/report` records the selected target and execution outcome | Offline checks verify target and honest interrupted/error outcome. Earlier real Docker reports separately prove353 actual pytest outcomes per runner and real failures against a different approved local target. |
| Unauthorized targets refused | Exact origin allowlist; wrong port/scheme, suffix spoof, credential spoof and arbitrary destinations400 INVALID_TARGET before session creation. Session retargeting and use after approval removal are refused. |
| Existing transport safety | Redirects disabled, proxies ignored, prepared requests confined to selected `/api/v1/` origin; system loopback/readiness/reset guards preserved. |

Application/runner code was already implemented and was not rewritten. The new
tests do **not** execute353 tests against public addresses: they stop before
process/network execution. The real353-case local results remain in
`artifacts/phase4-pod-update/adapters/{system,tester}-report.json`. The separate
`failing-report.json` names `http://broken:8080`, with353 actual failures and
zero passes, demonstrating selection of a different approved local target and
honest failure reporting rather than fallback to our own API. Original shared
OpenAPI, Team6 fixtures and157 original HTTP tests are unchanged.

Command actually run:

```powershell
python -X utf8 -B -m pytest tester-service/tests --ignore=tester-service/tests/test_http.py -p no:cacheprovider --junitxml artifacts/phase4-cross-team/offline.xml -q
```

Result: **97 passed** in2.30s, including9 new selection checks. The broader
non-destructive suite also passed: **445 passed** in5.99s, with one existing
third-party dateutil deprecation warning. Ruff lint/format (44 Python files),
mypy (13 production files), all three OpenAPI documents and `git diff --check`
passed. Bash `-n` accepted every Cloud Shell example; commands were not executed.
Collection-only verification confirmed353 portable cases in0.12s. All32 existing
non-documentation changed files match the preceding verified source hashes. Portable suite remains **353 =157 original+196 Phase4**. This additional
check has no new complete HTTP-suite, deployed or Team6 results; previous789/353 local
results are separately dated evidence. GitHub CI already collects these adapter
tests through its existing `pytest tester-service/tests --ignore=...` step.

## Explicit opt-in allowlist and prerequisites

`tester-service/cross-team.env.example` contains the exact two-target allowlist,
with both enable/reset flags **false**. It is not loaded automatically and does
not change the deployed service or weaken the Team2-only default:

```text
AUTOGRADER_DEFAULT_TARGET=https://cra-phase3-api-456725640364.us-central1.run.app
AUTOGRADER_APPROVED_TARGETS=https://cra-phase3-api-456725640364.us-central1.run.app,http://136.116.160.182:8080
AUTOGRADER_RUN_TIMEOUT_SECONDS=600
```

Before any public run, Team6 must confirm its current base URL, disposable data,
explicit reset authorization, fixture/source controls, compatible contract/errors,
deployed version and an exclusive UTC test window. Confirm which proposed Phase4
contract changes both services actually use. For the return direction Team2 must
also authorize resets of **cra_grading**, never retained `cra_phase3` or an OSV
production inventory. Use fixture mode for the reset-based353-case suite.

After separate deployment approval, an operator can set the allowlist above on
**cra-phase3-tester only**, preserving the existing report-only secret, SQL
attachment, runtime identity, timeout900, concurrency4 and other configuration.
Enable the controls only during the authorized window. Changing Cloud Run
environment variables creates a revision; this document is not permission to do
that now. Use the [paired deployment guide](deployment-phase4.md). Runtime image
and both suite files must be the reviewed Phase4 version, not an old157-case image.
The system keeps its loopback-only configuration and grading DB safety checks.

The current deployed allowlist/image was **not inspected or changed** here.
Setting variables in Cloud Shell alone does not alter the Cloud Run tester's
environment. Remove Team6 from the deployed tester allowlist after the window;
this requires a separately approved configuration revision as well.

The tester is publicly callable: while Team6 is allowlisted and reset controls
are enabled, any caller able to reach it can request a run against that approved
target. There is no per-session human approval mechanism. Keep the window narrow,
and coordinate access with Team6. Exact allowlisting is not a substitute for
their permission. A global PostgreSQL lock serializes our cooperating adapters
across both targets, but Team6's independent tester and direct CLI/test-control
calls do not share it. Run both directions sequentially with no other testers.

## Cloud Shell: Team2 tester → Team6 API

Run only after the prerequisites above are satisfied and the approved Phase4
tester is deployed. This is **Bash in Cloud Shell**, not PowerShell. Keep the
existing tester URL only after confirming it is the actual tester service.
The following defaults deliberately refuse execution until approval is recorded:

```bash
export CONFIRMED_TEAM6_URL='REPLACE_AFTER_TEAM6_CONFIRMS_CURRENT_URL'
export TEAM6_RESET_AUTHORIZED='no'
```

After receiving written permission and confirming the URL is still the exact
approved origin, set `CONFIRMED_TEAM6_URL` to that origin and
`TEAM6_RESET_AUTHORIZED=yes`, then run:

```bash
set -euo pipefail
TEAM2='https://cra-phase3-api-456725640364.us-central1.run.app'
TEAM6='http://136.116.160.182:8080'
TESTER_BASE='https://cra-phase3-tester-456725640364.us-central1.run.app'
TARGET_BASE="$TEAM6"
if [[ "${TEAM6_RESET_AUTHORIZED:-no}" != yes || "${CONFIRMED_TEAM6_URL:-}" != "$TEAM6" ]]; then
  echo 'STOP: confirm current Team6 URL and written reset permission first.' >&2
  exit 1
fi
RUN_ID="q61-team2-to-team6-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
EVIDENCE_DIR="artifacts/q61/$RUN_ID"
umask 077
mkdir -p "$EVIDENCE_DIR"
printf '%s\n' "$RUN_ID" > "$EVIDENCE_DIR/session-id.txt"
date -u +%FT%TZ > "$EVIDENCE_DIR/client-started-utc.txt"
jq -n --arg tester "$TESTER_BASE" --arg target "$TARGET_BASE" \
  '{tester_base_url:$tester,target_base_url:$target}' > "$EVIDENCE_DIR/targets.json"

# This discovery is the tester, not Team6. Confirm its role before setup.
curl --silent --show-error --connect-timeout 15 --max-time 30 \
  "$TESTER_BASE/test" > "$EVIDENCE_DIR/discovery.json"
jq -e '.role == "tester" and .enabled == true' "$EVIDENCE_DIR/discovery.json"

jq -n --arg id "$RUN_ID" --arg target "$TARGET_BASE" \
  '{session_id:$id,target_base_url:$target}' > "$EVIDENCE_DIR/setup-request.json"
STATUS=$(curl --silent --show-error --connect-timeout 15 --max-time 60 \
  -D "$EVIDENCE_DIR/setup-headers.txt" -o "$EVIDENCE_DIR/setup-response.json" \
  -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  --data-binary @"$EVIDENCE_DIR/setup-request.json" "$TESTER_BASE/test/setup")
printf '%s\n' "$STATUS" > "$EVIDENCE_DIR/setup-status.txt"
[[ "$STATUS" == 200 ]] || { cat "$EVIDENCE_DIR/setup-response.json"; exit 1; }
jq -e --arg id "$RUN_ID" --arg target "$TARGET_BASE" \
  '.session_id == $id and .target_base_url == $target and .role == "tester"' \
  "$EVIDENCE_DIR/setup-response.json"

# Destructive: the suite resets the approved Team6 target before every case.
# Selected target is stored in the session; no target override is needed here.
jq -n --arg id "$RUN_ID" '{session_id:$id}' > "$EVIDENCE_DIR/run-request.json"
STATUS=$(curl --silent --show-error --connect-timeout 15 --max-time 930 \
  -D "$EVIDENCE_DIR/run-headers.txt" -o "$EVIDENCE_DIR/run-response.json" \
  -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  --data-binary @"$EVIDENCE_DIR/run-request.json" "$TESTER_BASE/test/run")
printf '%s\n' "$STATUS" > "$EVIDENCE_DIR/run-status.txt"
[[ "$STATUS" == 200 ]] || { cat "$EVIDENCE_DIR/run-response.json"; exit 1; }

STATUS=$(curl --silent --show-error --connect-timeout 15 --max-time 60 \
  -D "$EVIDENCE_DIR/report-headers.txt" -o "$EVIDENCE_DIR/report.json" \
  -w '%{http_code}' "$TESTER_BASE/test/report?session_id=$RUN_ID")
printf '%s\n' "$STATUS" > "$EVIDENCE_DIR/report-status.txt"
[[ "$STATUS" == 200 ]] || { cat "$EVIDENCE_DIR/report.json"; exit 1; }
jq -e --arg id "$RUN_ID" --arg target "$TARGET_BASE" \
  '.session_id == $id and .target_base_url == $target' "$EVIDENCE_DIR/report.json"
jq '{session_id,target_base_url,status,result,summary,started_at,finished_at,duration_ms,runner_build_sha,tested_commit_sha,error}' \
  "$EVIDENCE_DIR/report.json"
jq '.checks | length' "$EVIDENCE_DIR/report.json"
jq '[.checks[] | select(.outcome != "pass") | {id,ac,outcome,actual}]' \
  "$EVIDENCE_DIR/report.json" > "$EVIDENCE_DIR/failures.json"
jq '[.checks | group_by(.ac)[] | {ac:.[0].ac,records:length}]' \
  "$EVIDENCE_DIR/report.json" > "$EVIDENCE_DIR/ac-counts.json"
date -u +%FT%TZ > "$EVIDENCE_DIR/client-finished-utc.txt"
printf 'Saved evidence: %s\n' "$EVIDENCE_DIR"
```

No `curl -L`, retries or automatic reruns are used. HTTP200 means an outcome was
returned, **not** that tests passed. Require the report's actual `result`,353
unique test records, expected files/AC groups and honest failure/error/skip counts.
Current Phase4 groups are AC04=10, AC05=11, AC06=62, AC07=113; originals total157.
Setup400 INVALID_TARGET means the exact origin is not approved in the deployed
tester; do not bypass it.409 means wait for the coordinated active run to end;
503 requires configuration/storage/readiness investigation.

If the client times out or loses the response, retain `RUN_ID`, do not create a
new destructive run, and poll only:

```bash
curl --silent --show-error --connect-timeout 15 --max-time 60 \
  "$TESTER_BASE/test/report?session_id=$RUN_ID" > "$EVIDENCE_DIR/report.json"
jq '{status,running,result,summary,error}' "$EVIDENCE_DIR/report.json"
```

Capture the actual runner SHA/image/revision separately. The report intentionally
leaves a remote target SHA unknown; obtain Team6's deployed SHA from Team6 rather
than inventing it. Preserve written permission and URL/window confirmation with
the evidence. The IP URL is plain HTTP: use synthetic disposable data, do not add
credentials or real incident information, and reconfirm access/auth notes with Team6.

## Team6 tester → Team2 API

Send Team6 this exact **system** target, not our tester URL:
`https://cra-phase3-api-456725640364.us-central1.run.app`.
Before inviting a run, Team2 must confirm the deployed reviewed Phase4 system,
`GET /test` role=system/reset_ready=true, actual disposable `cra_grading`, fixture
source mode, supported contract and a written exclusive reset window. Retained
`cra_phase3` and a production OSV inventory are not authorized targets.

Team6 must explicitly allowlist this origin in **its tester**, confirm its own
current tester URL/protocol and execute its **full** suite. Its test count is not
assumed to be353. For a Team6 tester that confirms the same `target_base_url`,
`session_id`, synchronous setup/run/report protocol, use the Bash pattern above
with these substitutions, after reciprocal permission:

```bash
TESTER_BASE='REPLACE_WITH_TEAM6_CONFIRMED_TESTER_BASE_URL'
TARGET_BASE='https://cra-phase3-api-456725640364.us-central1.run.app'
RUN_ID="q61-team6-to-team2-$(date -u +%Y%m%dT%H%M%SZ)"
# POST $TESTER_BASE/test/setup:
jq -n --arg id "$RUN_ID" --arg target "$TARGET_BASE" \
  '{session_id:$id,target_base_url:$target}'
# POST $TESTER_BASE/test/run: {"session_id":"the saved session ID"}
# GET $TESTER_BASE/test/report?session_id=the_saved_session_ID
```

These substitutions describe the request format, not a claim about Team6's live
protocol. If it differs, obtain its current access/run notes and use those; do
not guess its tester URL, methods, authentication or JSON schemas. CRA mutations
require nonempty X-User-Id; test controls are exempt. Share the unchanged pod
`docs/openapi.yaml` and separately identify pending Phase4 proposal differences.
Ask Team6 for full results, failure details and coverage artifacts using the
[Q6.1 template](phase4-q61-results-template.md). All actual cross-team results
remain pending until these authorized runs take place.
