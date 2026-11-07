# Cross-team testing interface

The source of truth is the **full course Cross-team Testing Interface v0.4.2 prose** ([supplied document](https://docs.google.com/document/d/1GhEVTw3a2tNJY2arfDyWgWS94kVYfgC7/edit)), including execution, coverage, error and concurrency rules. Its minimal OpenAPI starter is insufficient by itself. The earlier peer OpenAPI was provisional and is superseded. Project behavior, fixtures, resets and acceptance criteria come from the [pod Phase 2 specification](https://docs.google.com/document/d/1jRBiYWWyYGn-SjoQ4pHxduenk8bkCmpJAyVD0Wt8SP8/edit), especially Q4.1 and Q5.3. The domain contract remains [openapi.yaml](openapi.yaml).

Complete role-specific schemas: [tester](autograder-openapi.yaml) and [system](system-test-openapi.yaml). Each running service incorporates its role's schemas in `/openapi.json`, using namespaced components to preserve the project API schemas.

## Calls and lifecycle

1. Tester `POST /test/setup` requires `{"target_url":"https://system-base"}`. It authorizes that URL using the existing exact allowlist, generates a UUID, and sends `{"session_id":"<same UUID>","setup":{}}` to **that target's** `/test/setup`. It waits for 201 and the same ID before returning 201 `{"session_id":"..."}`. No suite runs during preparation.
2. System `POST /test/setup` requires `session_id` and an object `setup`. It checks the disposable database identity, clears CRA test data, prepares the baseline, and returns that supplied ID with 201. Existing IDs return 409, including failed preparation IDs. Failed preparation returns 500 with `message` and `source:"system"`. Tester forwards a valid upstream error's status/message/source unchanged and leaves no runnable tester session.
3. Tester `POST /test/run` requires `{"session_id":"..."}`. It runs the existing **353** Phase 3/4 tests, retrieves system code coverage by the same ID, persists the complete report, and returns it with 200. Evaluated test failures and system/communication errors are results; they do not themselves turn a completed batch into HTTP 500.
4. Tester `GET /test/report?session_id=...` returns 409 until execution ends, then 200 with the immutable stored report. It never runs, repeats, recovers or edits tests. Concurrent and later runs return 409, including after an abort. Invalid requests do not consume a ready session.
5. A tester abort returns 500 `{"message":"...","source":"tester"}` after saving available results. Completed outcomes remain; an active test prevented from evaluation becomes `error`/`tester`; remaining unexecuted tests are `skip`. A fresh setup/ID is needed to run again. Following a lost response, poll report rather than retry run. A process crash may leave no retrievable report, as the course prose allows; lookup does not fabricate one.
6. System `GET /test/report?session_id=...` returns only `session_id` and `coverage.code`, with 409 while preparation is in progress. It does not run tests. It can report direct staff project requests without a tester batch. Reading coverage is observational; later project calls may increase it. A system `/test/run` is not exposed.

Tester report shape:

```json
{
  "session_id": "a-unique-id",
  "target_url": "https://system-base",
  "results": [
    {"test_id":"a-unique-test-id","outcome":"pass","message":"Expected behavior observed."}
  ],
  "coverage": {
    "code": {"covered":null,"total":null,"basis":"Source instrumentation unavailable on this target"},
    "component": {"covered":null,"total":null,"basis":"Shared pod component denominator and exercise rules unavailable"},
    "system": {"covered":7,"total":10,"basis":"Pod AC-01–AC-10; mapped scenario inputs dispatched, independent of outcomes"}
  }
}
```

The one-result excerpt above illustrates the format, not the complete suite. Every planned test appears exactly once, in order, with a nonempty ID/message. Outcomes are `pass`, `fail`, `error`, `skip`; `error` also requires `source` (`tester`, `system`, `communication`, `unknown`). Expected project errors are passing behavior. Unexpected target internal errors are `error/system`; no-response transport failures are `error/communication`. Each coverage entry contains nonnegative integer counts with covered <= total, or **both null** and a reason in `basis`. Coverage is not a pass rate. See [coverage scope and limitations](coverage-measures.md).

## Supported requests and errors

- The exact rejected grader body `{"target_url":"https://cra-phase3-api-456725640364.us-central1.run.app"}` is supported, subject to enabled controls, explicit target approval and successful system preparation. The end-to-end regression routes that literal hostname to an isolated local target; it does not contact the public service.
- Tester optionally accepts `setup:{...}` and forwards that object unchanged. This is our extension for pod starting data, not a required tester request field. Our system accepts `{}` or an optional `now` RFC 3339 UTC/offset clock in that object; each test subsequently sets its own deterministic fixture clock. Other systems define their own starting data.
- Bodies must be JSON objects. Missing/invalid fields, duplicate keys, extra top-level fields, query parameters on POST, GET bodies and missing/duplicate report IDs return 400. Legacy `target_base_url`, caller-supplied tester IDs, implicit/default targets, empty setup requests and query-based setup/run are unsupported under the supplied contract. Unknown metadata is not silently discarded or treated as target selection.
- Existing target validation remains: exact approved HTTP(S) origins, optionally entered with `/api/v1`, normalize to the origin. Embedded credentials, query strings, fragments and arbitrary path prefixes are refused. Path-prefixed project deployments need an explicit future transport change; their support is not claimed. Redirects and inherited proxies are disabled on preparation, suite and report calls. Arbitrary targets never fall back to the default service.
- Test endpoint errors use top-level nonempty `message` and `source`: 400 invalid, 404 unknown ID, 409 conflict/not ready, 500 service failure/abort. Valid system setup errors preserve their upstream status/source. Domain `/api/v1` errors retain the separate pod error contract.
- Source details, request values, secrets and tracebacks are not logged by adapter errors. Tester child diagnostics are redacted; child environment excludes database/password/token/credential variables. Upstream setup messages are forwarded as required by the interface.

## Preparation, isolation and retention

This implementation uses one global disposable CRA database/clock, as in pod Q5.3, **not one database per ID**. Setup resets that state. Tests reset before each case and create prerequisites in order. Only cooperating adapters share the PostgreSQL advisory setup/run mutex. A run holds it through all project calls and coverage retrieval; setup RPC releases the tester mutex so system setup can acquire it without deadlock. Overlapping controls return 409. Only one tester session may be pending across cooperating adapters: another setup is refused until it completes or aborts, preventing a ready suite from losing its baseline. An interrupted pending record may require deliberate operator cleanup after confirming no run remains. IDs link tester/system metadata and coverage; they are not authentication or a data partition.

A later setup replaces the global target baseline. Use exclusive target windows and do not leave older prepared sessions pending while preparing another. Instrumented requests carry our optional `X-Test-Session-Id` header; stale IDs are rejected before project execution, and prior coverage freezes before replacement. Untagged peer/direct project requests belong to the current session; direct CLI resets and other teams that bypass our mutex require coordination. The unchanged pod project API cannot fence such callers. No simultaneous independent target sessions are promised.

`cra_autograder` stores both roles' JSON records independently of `cra_grading`, so domain resets cannot erase reports. Completed tester reports remain immutable and survive normal tester restarts; the contract only requires retention until instance stop. Source collection lives on one system process: prior-session snapshots are frozen at the next setup, terminal tester reports persist retrieved counts, and a restarted/lost collector reports unavailable rather than mixing sessions. No automatic report cleanup is introduced.

New records identify interface version 0.4.2. Earlier records remain untouched;
legacy tester sessions return 409 directing callers to a new setup instead of
being run or synthesized into the new report format. They do not reserve the
new protocol's pending-session window. Drain old revisions before rollout so
their older setup/run behavior cannot overlap the new lifecycle.

The grading entrypoint starts its control routes without opening the project database; schema initialization occurs inside system setup after validating the disposable database identity. Thus setup remains reachable when the project database is unavailable and returns the required 500/system envelope. Report storage uses the separate metadata database. Successful preparation still requires that disposable domain database to be available. The normal production startup/retry lifecycle is unchanged. Failed setup never starts the suite. Controls default disabled and resets default unauthorized; enabling both is authorization to erase approved disposable data, not retained production data.

## Timing and deployment

Register tester setup **65 seconds**, system setup **60 seconds**, tester run **600 seconds** (configure `AUTOGRADER_SETUP_TIMEOUT_SECONDS=60`, `AUTOGRADER_RUN_TIMEOUT_SECONDS=600`, Cloud Run request timeout >=900). Target project calls retain the pod fixtures' 15-second timeout and no implicit retry. The tester run budget includes coverage retrieval. When exhausted, the stored aborted report may contain null code counts explaining why retrieval was not possible.

For measured source coverage, build the system Docker `grading` target and set `AUTOGRADER_COVERAGE_ENABLED=true`; use one worker, one replica and request concurrency >=2. Tester needs no shared coverage secret or coverage-origin side channel: it reads the contract's system report. Existing legacy coverage env settings are ignored. Ordinary production images report source coverage unavailable honestly. The earlier deployment guide's private coverage-secret rollout is superseded; do not execute it unchanged. This PR does not deploy, change registry entries or reset public data.

## Local verification

Install `cra-service/requirements-dev.txt`. Adapter unit/ASGI contracts run with:

```sh
python -m pytest tester-service/tests --ignore=tester-service/tests/test_http.py --ignore=tester-service/tests/test_grading_http.py -q
python -m ruff check cra-service tester-service scripts
python -m ruff format --check cra-service tester-service scripts
python -m mypy
```

CI creates a fresh Compose project using `tester-service/docker-compose.test.yml` plus `docker-compose.contract.yml`, a temporary test-only TLS CA and an internal network. The exact public hostname resolves to the local TLS bridge, with no Internet route from the tester/system containers. A fixed-destination access relay publishes loopback-only test ports. `test_http.py` verifies exact target selection, same-ID forwarding, both reports, readiness, repeated-run rejection, setup failure forwarding and partial-result abort behavior. `test_grading_http.py` verifies genuine direct server execution, read-only snapshots and consecutive-session isolation. Run these only with the documented isolated stack flags, never against public services. The suite plan is pinned to the two preserved domain test files and their conftest; regenerate it from collection if those sources change.
