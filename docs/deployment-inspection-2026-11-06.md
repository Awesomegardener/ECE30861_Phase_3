# Read-only deployment and registry inspection

This records the pre-publication inspection. The later review replaced the
local-only collector with a [Cloud Run grading configuration](autograder-coverage-deployment.md).
It has not been deployed; the observations below are unchanged historical evidence.

November 6, 2026. No public setup, run, domain mutation/reset, deployment, registry
edit or Cloud resource change was performed.

## Registered entry and public availability

The connected Google Drive/Sheets account could read
[Endpoint Registry](https://docs.google.com/spreadsheets/d/1bTCN3IdCcOPDYIAh7nG7WKNnv9WaAfbdkWfnnK97HL4/edit),
tab `Endpoints` (`sheetId=508969597`), row 25 (West Lafayette / Pod J / Team 2).
The exact checked range was `A25:H26`, after metadata/header discovery.

| Field | Registered value | Read-only verification |
| --- | --- | --- |
| System E25 | `https://cra-phase3-api-456725640364.us-central1.run.app` | GET `/test`, `/health/ready`, `/openapi.json`: 200; discovery identifies system and reset_ready true |
| Tester F25 | `https://cra-phase3-tester-456725640364.us-central1.run.app` | Same GETs: 200; discovery identifies tester and reset_ready false |
| Shared specification G25 | GitHub `Awesomegardener/ECE30861_Phase_3/blob/main/docs/openapi.yaml` | Raw linked file returned 200 without authentication; bytes exactly match local shared specification |
| Access notes H25 | November 1 Phase 4 update; 353 cases, no authentication, 600-second execution/900-second HTTP budget, client allowance 930 seconds, resets require coordinated windows | GETs worked with no credentials. No write route was called to prove its deployed authentication behavior; local route definitions require no `/test*` caller credentials. |

The bases are distinct services with no extra `/test` suffix. The shared spec
SHA256 is `4739211030ed18d7e80c098048d11ae2bc422828f3423cb3236b8a111900026f`.
This proves current public retrieval, not continuous availability during October
28–29, approved pod changes, or the deployed source revision.

## Discrepancies and limits

1. Both deployed `/openapi.json` documents advertise successful `/test/setup` as
   **200**, whereas grading expects **201** and this local branch advertises 201.
   No public POST was made; the observation concerns the deployed documentation,
   not a newly measured setup status. The local fix still needs paired rollout.
2. GET tester `/test/report` returned a stored **341/353 pass** report, result
   `fail`, runner SHA `9e1dae298eaa4e09fd94d0e86366d37ba37f6806`, finished
   `2026-11-02T00:35:33.439079Z`, against **Team 6's** registered system
   `http://136.116.160.182:8080`. It contains no `coverage` field. Its twelve
   failures concern UTF-8/error-message wording, JSON media type and timestamp/CVE
   boundary differences. These are stored cross-team observations, not a new
   execution or proof that either team's shared interpretation should change.
3. H25's 353/353 claim expressly concerns our deployed system. The latest stored
   report concerns another target, so it does not refute that historical claim;
   this inspection did not reproduce it. Do not relabel the peer report as an
   own-system failure or claim a fresh hosted pass.
4. GET system `/test/report` without an ID returned 404. This means no latest
   system-role session was available through that lookup. It is not evidence
   that an existing valid system-session ID would fail. Separate role namespaces
   remain relevant to staff's unconfirmed tester/system session protocol.
5. The registered specification is the shared CRA domain contract. It does not
   establish a complete staff tester request/report schema. Link the separate
   adapter documentation in access notes after a reviewed update; do not replace
   the shared domain specification with our provisional adapter schema.

## Authenticated Google Cloud access and historical logs

Deployment configuration identifies project `cra-vulnerability-service`, region
`us-central1`, Cloud Run services `cra-phase3-api` / `cra-phase3-tester`, Cloud SQL
instance `cra-phase3-pg`, and separate grading/report databases. Existing build
files are build-only and do not deploy. No secrets were opened or printed.

No `gcloud` executable or local credential directory was found in the checked
standard locations. Computer-use inventory reported the browser access host
unavailable, and the native Brave access attempt timed out. Plugin discovery
also found no relevant Cloud Logging connector. Thus no usable
authenticated Cloud Console/Logging session was established. Cloud Logging was
**not searched**, and no unknown field names/request body were recovered.

When an authorized Cloud session becomes available, use a read-only Logs Explorer
query in the existing project, with a padded window covering October 28–29 UTC
and Eastern (EDT) dates:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="cra-phase3-tester"
timestamp >= "2026-10-28T00:00:00Z"
timestamp < "2026-10-30T04:00:00Z"
(
  (httpRequest.requestMethod="POST" AND httpRequest.requestUrl:"/test/setup")
  OR textPayload:"Unexpected request fields"
  OR jsonPayload.message:"Unexpected request fields"
)
```

Inspect matching request status, revision and correlated application logs. Record
query parameter **names only**, if present; do not copy URL parameter values,
headers, tokens, credentials or request bodies into documentation. The old
adapter returned the generic unknown-field error without logging field names.
System request middleware recorded path/status but no body; tester uvicorn access
logs might contain a query string if the grader used one. Standard Cloud Run
request logs do not establish a missing JSON body. A missing application record
cannot be reconstructed as a request. Retention/permissions may also limit recovery.

## Evidence and rollout preparation

Ignored local artifacts under `artifacts/autograder/`:
`public-readonly-inspection.json`, `public-report-readonly-inspection.json`, and
`public-latest-report-failures.json`. The registry was read through the connected
Sheets account; its entry was not modified.

After explicit rollout approval, build paired production images from the same
reviewed commit using the existing Cloud Build files. The default final Docker
stage remains production; do not select `isolated-coverage` for Cloud Run. Keep
current URLs, secrets, grading/report storage and allowlists. The local coverage
collector is not a production coverage service and cannot supply remote peer
source coverage. Follow `deployment-phase4.md` for ordered rollout and rollback.

Coordinate a separate authorized exclusive reset window before any hosted
setup/run. Record deployed SHAs/digests, 201/200/200 behavior, session IDs, exact
response schemas and target-specific results. Update H25 only after verifying
those facts, with clear target/source coverage limitations. Staff still needs
to clarify request fields, cross-role session linkage and scorable coverage schema.
