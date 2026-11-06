> Phase4 Q6.1 addition: see [phase4-cross-team-testing](phase4-cross-team-testing.md). Bidirectional target support is verified offline; actual public runs and live allowlist configuration remain pending authorization.

# Team 2 HTTP autograder adapter

This extension is independent Team 2 code. The provisional external reference is
[Team 6 OpenAPI](https://github.com/sanjayriram44/ReleaseGate/blob/9c0b1917b6ed316d51b412685805bd8766b8edea/docs/openapi.yaml)
and [README](https://github.com/sanjayriram44/ReleaseGate/blob/9c0b1917b6ed316d51b412685805bd8766b8edea/README.md),
read October 26, 2026. Only those two documentation files were consulted; no peer
implementation, tests or database design was copied. This is compatibility
evidence, **not documented instructor approval**. Our original CRA contract and
Team 6 fixtures are unchanged. The new interface is specified separately in
`autograder-openapi.yaml`. The November 1 Phase 4 extension adds the contract's
CVE/incident operations and a second HTTP test file; Phase 5 remains deferred.

## Confirmed requirements and assumptions

The staff announcement supplied by the user requires distinguishable deployed
system/tester URLs, reachable October 28–29, 2026, and registry updates by
**October 27, 11:59 p.m. Eastern**. Staff append `/test`, `/test/setup`, `/test/run`
and `/test/report`; the shared specification and authentication notes must be
accessible. The announcement does not establish full schemas or execution rules.

November 6 grading feedback confirms successful setup must return **201**;
run and report return **200**. Both adapters now implement this correction.
The grader's rejected request body/query and complete request/report schemas
are still unavailable. See [fix evidence and rollout notes](autograder-fix.md).

We provisionally adopt Team 6's GET discovery, POST setup, synchronous POST run,
GET report, JSON/query input, generated or supplied session identifiers, latest
session defaults, 400/404/409 envelopes, and ready/completed/pass/fail/error
structure. Both roles expose these paths. Confirm this protocol with staff.

Intentional Team 2 choices:

- All **157 unchanged Phase 3 cases plus 196 Phase 4 cases (353 total)** are required.
  The runner checks expected collection count and reports AC-01 through AC-07.
  We do not adopt Team 6's smaller
  suite, informational classifications, nested-component implementation or
  "under 30 seconds" performance promise. Historical hosted execution was about
  104 seconds; the subprocess budget is 600 seconds, HTTP deployment budget 900.
- The target is an exact approved origin (optionally entered with `/api/v1`).
  Tester defaults approve only Team 2's grading origin. Team 6 requires explicit
  allowlist configuration during a coordinated reset window and removal afterward;
  an existing environment override is not changed by deploying a new image.
  Credentials, arbitrary paths, query strings and fragments are rejected. Only
  operator-configured Team 2/Team 6 targets are allowed, plus explicitly configured
  loopback/container origins for isolated/self testing. No user-controlled shell
  commands, pytest arguments, file paths or executable names are accepted.
  A harness-only pytest plugin checks every prepared request, disables all
  redirects and ignores environment proxies. This includes new sessions used
  by the intentional concurrent test. The original CLI fixtures are unchanged.
- System self-tests use only `http://127.0.0.1:PORT` (8080 by default), never a
  public fallback, remote hostname or different port, even if allowlisted.
  Adapter resets require both the exact `cra_grading` database name in config
  and the actual connection; a retained/course database cannot be selected.
  Our public URL must additionally advertise `role: system, reset_ready: true`
  before the tester launches pytest. An older/unready Team 2 revision is refused
  without issuing a reset. This is an optional Team 2 discovery extension, not a
  requirement imposed on Team 6's independent protocol. Tester discovery returns
  `reset_ready: false`; it does not own a domain database.
- Session IDs contain 1–128 letters, digits, `_`, `.` or `-`. Existing IDs cannot
  be replaced: setup returns 409. Completed run retries return the stored result;
  a new setup/session is required to rerun. A session's target is immutable.
- Setup/run accept JSON objects or equivalent query fields. Conflicting body/query
  fields, unknown fields and invalid input return 400. `now` belongs to system
  setup only; valid RFC 3339 offsets normalize through the original clock model.
  Each unchanged pytest case subsequently resets and sets its own fixture clock.
  Unknown-field errors and warning logs now list bounded top-level field names
  and JSON types plus accepted fields in the response. Values and nested content
  are omitted; unusual names are redacted. Rejected inputs create no session and
  launch no child. Unknown target names are never mapped to the default target.
- Run without an ID uses the latest session; if no session exists, it creates one.
  An explicitly unknown ID returns 404. Reports without an ID use the latest
  session **for that role**. System and tester session IDs need not be shared.
- During execution reports remain `status: ready`, with `running: true` and no
  success result. This preserves the reference status enum. Timeouts, incomplete
  collection, missing XML, fixture errors and interruptions return `result: error`.
  These are extensions/clarifications, not newly agreed pod requirements.
- Configuration/storage failures return a non-secret 503 envelope. Setup collisions
  return 409 as well as active-run collisions. These extra responses are documented
  in our extension; they do not alter the original CRA API errors.

## How it works

```mermaid
flowchart LR
  Staff --> S[Existing CRA system /test adapter]
  Staff --> T[Separate HTTP tester /test adapter]
  S --> M[(Shared report database and execution lock)]
  T --> M
  S --> P[Fresh pytest subprocess: 157 original plus 196 Phase 4 tests]
  T --> P
  P --> C[Explicitly approved disposable CRA target]
```

Both services use our `cra-service/autograder/` package. The system also serves a
JSON homepage. Its adapter calls a separate, opt-in reset function; the original
`/api/v1` routes retain their behavior. System setup verifies the connected
database is `cra_grading`, then resets domain data and applies an optional clock in one SQL
transaction. Phase 4 adds incident/submission/test-source tables; reset clears
all domain test state. Tester setup only selects a target;
run executes the existing suite, which resets that target before **every case**.

A fresh `python -m pytest cra-service/test_api.py cra-service/test_phase4_api.py` subprocess writes JUnit and
bounded redacted HTTP evidence in a unique temporary directory. Collection remains
353 cases; support-boundary and duplicate-registration tests now also assert their
before/after state for model witnesses. Runs are sequential; the existing
intentional concurrent SBOM replacement test still runs its own two requests.
The child does not inherit database URL/password/token/credential environment
variables. No target commit is invented: reports identify runner BUILD_SHA when
available and leave target SHA unknown. JUnit determines test outcomes; HTTP
examples alone do not establish passing assertions.

Each check contains a JUnit ID/title, AC group, required/passed flags, expected and
actual assertion outcome, and an HTTP example when available. AC grouping is a
reporting aid; the original test names/assertions are authoritative. Summary
counts expose passed/failed/errors/skipped and required/informational totals.
Skipped/incomplete suites cannot pass. Count-correct XML with duplicate identities,
wrong test-file counts or missing Phase 4 acceptance groups is also rejected as
an error. JUnit teardown errors may add records beyond the 353 collected cases.
Reports retain per-test outcomes and
representative redacted request/response evidence; complete temporary log/XML/body
files are removed after parsing, not retained as durable downloadable artifacts.

Reports include a Team 2 `coverage` diagnostic extension. The explicit grading
image/profile collects authenticated target execution during each run and saves
source/branch measurements, component witnesses, proposed model transitions and
a compressed trace directly with the completed session before responding. No
Docker-only importer or shutdown hook is involved. See
[definitions and instrumentation](coverage-measures.md). It uses the same
request-driven code intended for Cloud Run; actual hosted rollout is not claimed.
It does not establish the grader's report schema. Targets without explicitly
configured instrumentation report unavailable, not invented coverage.
Measured `http_operations` counts each operation in the
unchanged shared OpenAPI receiving at least one HTTP response in the full run
(including failures). It records the specification hash, observed/total counts,
missing operations and status counts. It is an API observation metric, not code,
component or state/transition coverage and not a confirmed grader report schema.
No setup, interrupted run or legacy report gains an invented measurement.

The [exact grading deployment configuration](autograder-coverage-deployment.md)
requires a single worker/replica, concurrency greater than one, a new service
secret shared only by the two Team 2 services, and existing isolated grading/report
storage. Internal coverage controls are authenticated and excluded from OpenAPI.
No additional caller authentication is imposed on public `/test*` paths.

## Persistence and interference boundaries

Use one metadata database, `cra_autograder`, on the **existing** Cloud SQL instance,
shared by both roles and all revisions. It contains only `autograder.sessions`;
no new paid instance, Redis, queue or object-storage service is required. CRA
reset cannot erase it. Reports persist across process/instance restarts and have
no automatic expiry; retain through grading and clean them up manually afterward.

A PostgreSQL session advisory lock permits one adapter setup/run at a time across
both services/targets. Overlapping operations return 409. Ordinary report reads
do not contend for this lock. The runner checks its lock connection while the
child runs and terminates the child if that connection fails. Normal shutdown
terminates active children; hard container termination kills its processes. A
persisted abandoned running record is recovered as completed/error on the next
report/control request. An infrastructure failure may require retrying report
retrieval after database connectivity returns; execution is never resumed halfway.

This mutex protects **cooperating adapters**. Original `/api/v1/test/reset` and
`/api/v1/test/clock` must remain compatible, so direct CLI tests, Team 6's tester
or manual calls can still interfere. A session ID is reporting metadata, not a
private partition of the global release/clock tables. Arrange exclusive target
windows with Team 6 and avoid manual/CLI resets during grading. Under a database
network partition a failed lock connection is detected on the next heartbeat;
there is no distributed fencing of the unchanged domain endpoints.

The evaluation target must contain disposable synthetic data. Adapter controls
default disabled, and reset permission defaults false. Enabling them is an
operator authorization to erase the approved target during runs. For retained
cloud data, create a separate empty grading database and switch only the approved
evaluation revision after review. Do not point local tests at the public service.

## Local checks

Run from the repository root (PowerShell example). The new Compose project uses
ports 18086/18087, its own PostgreSQL volume, and an intentionally broken local
target. It never connects to Cloud SQL or Team 6.

Use a **new project name** for the updated dual-database test configuration.
Its init SQL creates ordinary grading/report roles only on a fresh volume. Do
not reuse/delete an old volume to make initialization run. Earlier stacks using
the single `cra_test` DB are retained and should remain stopped; their setup
does not match the revised test configuration. The original CRA-only Compose
files still use their existing settings and volumes with adapter controls off.

```powershell
python -m pip install -r cra-service/requirements-dev.txt
docker compose -p cra-phase3-autograder-local -f tester-service/docker-compose.test.yml up --build -d --wait
python -m pytest cra-service --allow-reset --base-url http://127.0.0.1:18086 -q
python -m pytest tester-service/tests --ignore=tester-service/tests/test_http.py -q
$env:HARNESS_INTEGRATION='1'
$env:HARNESS_SYSTEM_URL='http://127.0.0.1:18086'
$env:HARNESS_TESTER_URL='http://127.0.0.1:18087'
python -m pytest tester-service/tests/test_http.py -q
python scripts/check_autograder_runtime.py --project cra-phase3-autograder-local
python -m ruff check cra-service tester-service scripts
python -m ruff format --check cra-service tester-service scripts
python -m mypy
docker compose -p cra-phase3-autograder-local -f tester-service/docker-compose.test.yml stop
```

Do not run the CLI suite and adapter HTTP suite simultaneously. To validate
responses against the pinned external documentation as well as our own schema,
download **only that OpenAPI documentation** to an ignored artifact file and set
`TEAM6_AUTOGRADER_SPEC` to its path before `test_http.py`. CI validates our own
extension without depending on mutable external URLs. Actual local results are
recorded in `testing.md`; a locally passing workflow is not a GitHub Actions run.
