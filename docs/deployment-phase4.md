> Phase4 Q6.1 addition: see [phase4-cross-team-testing](phase4-cross-team-testing.md). Bidirectional target support is verified offline; actual public runs and live allowlist configuration remain pending authorization.

# Phase 4 paired deployment plan (not executed)

**November 6 autograder review:** use the [grading coverage rollout](autograder-coverage-deployment.md)
for this fix. It adds an explicit `grading` image/entrypoint, authenticated
request-driven measurement and a new shared service secret. The older commands
below omit those settings and do not enable measured grading reports. The
commit/push/PR is now authorized; cloud builds, secrets/IAM, deployment and
public resets remain separate approvals. Preserve actual current rollback
revisions rather than assuming the historical SHA below is still current.

Review/approval gate: do not run cloud commands until the user approves commit,
push, builds and deployment. Local implementation is not public verification.
Keep both existing URLs, existing Cloud SQL instance, `cra_grading` domain DB,
`cra_autograder` reports, and the untouched retained `cra_phase3` DB.

## 1. Review and local verification

From the repository root with Docker Desktop running, choose a new project and
unused loopback ports. Never reuse or delete any existing Docker volume. Example:

```powershell
$project = 'cra-phase3-autograder-phase4-example01'
$env:HARNESS_SYSTEM_PORT = '18106'
$env:HARNESS_TESTER_PORT = '18107'
$env:HARNESS_SENTINEL_PORT = '18112'
docker ps -a --filter "label=com.docker.compose.project=$project"
docker volume ls --filter "name=$project"
# Continue only if this project/volume does not exist and ports are unused.
docker compose -p $project -f tester-service/docker-compose.test.yml up --build -d --wait --wait-timeout 240
python -X utf8 -B -m pytest cra-service tester-service/tests --ignore=tester-service/tests/test_http.py --allow-reset --base-url http://127.0.0.1:18106 --capture-http-bodies --evidence-dir artifacts/phase4/final --junitxml artifacts/phase4/final.xml -p no:cacheprovider -q
$env:HARNESS_INTEGRATION = '1'
$env:HARNESS_SYSTEM_URL = 'http://127.0.0.1:18106'
$env:HARNESS_TESTER_URL = 'http://127.0.0.1:18107'
$env:HARNESS_SENTINEL_URL = 'http://127.0.0.1:18112'
$env:HARNESS_EVIDENCE_DIR = 'artifacts/phase4/autograder'
python -X utf8 -B -m pytest tester-service/tests/test_http.py -p no:cacheprovider -q
python scripts/check_phase4_runtime.py --project $project --base-url http://127.0.0.1:18106 --evidence-dir artifacts/phase4
python scripts/check_autograder_runtime.py --project $project --tester-url http://127.0.0.1:18107 --timeout-port 18108 --unsafe-port 18113 --evidence-dir artifacts/phase4/autograder
python -m ruff check cra-service tester-service scripts
python -m ruff format --check cra-service tester-service scripts
python -m mypy
python -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/phase4/final
git diff --check
docker compose -p $project -f tester-service/docker-compose.test.yml stop
```

Use the active virtual environment's Python (`.venv/Scripts/python.exe` on Windows).
Run commands sequentially; stop after any failure. Integration checks reset only
this new grading DB. Stopping services retains the new volume and all evidence.
Original Compose development stack remains unchanged; its source controls stay
disabled by default. The isolated Compose files explicitly enable synthetic CVEs.

## 2. Confirm current deployment and database isolation in Console

Select project **cra-vulnerability-service**, region **us-central1**. In Cloud
Run open **cra-phase3-api** and **cra-phase3-tester**. Record current image digests,
100%-traffic revision names, IAM, probes, CPU/memory, secrets/numeric versions and
Cloud SQL attachment. Both services already exist per the user; do not create new
services or guessed URLs. Existing addresses:

- System: `https://cra-phase3-api-456725640364.us-central1.run.app`
- Tester: `https://cra-phase3-tester-456725640364.us-central1.run.app`

In Cloud SQL open **cra-phase3-pg**. Verify the existing system's DATABASE_URL
secret references **cra_grading**, not **cra_phase3**, and its ordinary role owns
the domain tables. Read only secret configuration through authorized Console
access; do not log/paste DSNs. Confirm tester has only the metadata DSN, both use
the same **cra_autograder** DB, and the two DB roles have no cross-DB privileges.
If any differ, stop and reconcile using `deployment-tester-google-cloud.md`.
Do not rerun its initial CREATE ROLE/DATABASE instructions on existing resources.

The system role needs USAGE/CREATE on its grading `public` schema and ownership
of the existing domain tables/indexes. Existing Cloud SQL Client and secret-level
Secret Accessor permissions remain sufficient. No new secret is required for
deterministic CVE grading. No Dependency-Track API key/integration is introduced.
Do not add privileges on, initialize, migrate or reset **cra_phase3**.

New tables/indexes are initialized automatically in one transaction under the
existing startup advisory lock, preserving releases/SBOMs. The main new objects
are `incidents`, `incident_submissions`, `test_vulnerability_source` and the four
OSV tables described in `osv-snapshots.md`. OSV tables can be empty in fixture mode. The app
refuses startup against the retained DB before DDL. Startup on the grading DB
may briefly contend on locks; schedule an exclusive test/rollout window and keep
the startup probe budget. No down migration is needed for rollback: old code
ignores additive tables. Stop new testers on rollback because the old reset does
not clear Phase 4 rows.

## 3. Build both images from the same approved commit

After separate commit/push approval and a passing GitHub workflow, use the existing
two build-only Cloud Build triggers. In Console choose the exact reviewed SHA
for both builds, system config `cloudbuild.yaml`, tester config
`cloudbuild-tester.yaml`, repository-root Docker context. Keep existing build
identity, Artifact Registry and region; record build URLs and image digests.

PowerShell equivalents on a workstation with gcloud installed and existing
authorized authentication (replace trigger names with the existing Console names):

```powershell
$phase4Sha = 'REPLACE_WITH_APPROVED_FULL_SHA'
$systemBuildTrigger = 'EXISTING_SYSTEM_BUILD_TRIGGER'
$testerBuildTrigger = 'EXISTING_TESTER_BUILD_TRIGGER'
gcloud builds triggers run $systemBuildTrigger --project=cra-vulnerability-service --region=us-central1 --sha=$phase4Sha
gcloud builds triggers run $testerBuildTrigger --project=cra-vulnerability-service --region=us-central1 --sha=$phase4Sha
```

Use the triggers' actual region if different; both must build this same SHA.
Images use existing `us-central1-docker.pkg.dev/cra-vulnerability-service/cra-phase3/`
repository, names `cra-api` and `cra-tester`. Pin digests after successful builds;
do not deploy a moving `latest` tag. No cloud build or deployment was run locally.

## 4. System candidate first; tester second

### Compatibility during independent service updates

The services can be updated in separate deployment operations, but arbitrary
order is not compatible. Pause all automated/manual/peer runs and let active
sessions finish before changing either service. Preserve both existing public
URLs and report database; record each prior revision/digest independently.

| Public system | Public tester | Compatibility during the window |
|---|---|---|
| Phase3 | Phase3 | Existing157-case baseline only |
| Phase4 | Phase3 | Original157-case suite remains supported, but its result does not certify Phase4; keep external testing paused |
| Phase3 | Phase4 | Not a supported testing pair:353 cases require new routes/source behavior; do not enable/promote the new tester first |
| Phase4 | Phase4 at the same reviewed SHA | Intended353-case grading pair; requires fresh sessions and approved verification |

Safe order is system candidate/read-only checks, approved system promotion, then
tester candidate/approved full verification and tester promotion. Until the pair
is verified, do not advertise Phase4 readiness or invite peer testers. A0%-traffic
candidate still initializes the shared grading schema and is not data-isolated.
The additive domain schema and original157 regression results support the
system-first transition; there is no automatic cross-service version negotiation
or Phase4 capability gate. The Team2 `reset_ready` signal checks disposable DB
safety, not that the target implements every Phase4 route.

Reports are versioned evidence, not upgrade migrations: completed historical
sessions are cached and can still contain157 checks. Always create new session
IDs after upgrade and inspect actual count, runner SHA and target. Stop new
Phase4 testers before rolling the system back. Restore the old tester first (or
keep it disabled) before directing the system back to Phase3; keep testing paused
until the pair is compatible. Existing additive rows remain; do not run an old
reset against Phase4 data expecting it to clear new tables.

Coordinate with Team 6, suspend scheduled/manual tests, wait for active sessions
to finish, then open Cloud Run > **cra-phase3-api** > Edit & deploy new revision.
Select the new system digest, initially **no traffic**, tag `phase4-system`.
Zero percent traffic isolates HTTP routing, **not the shared database**. Startup
still creates additive objects in `cra_grading`; `/test/setup` and `/test/run`
on the tagged candidate would clear that same live grading DB. A URL tag does
not provide data isolation. Do not run those controls while real clients use it.
Preserve service account, Cloud SQL connection, numeric secret references,
public IAM and existing settings. Use 8080, 1 vCPU/1 GiB, second generation,
request billing, max 1, concurrency 8 and request timeout 900 seconds. Keep startup
`/health/ready`, liveness `/health/live`, and the existing supported probe budgets.
The child limit stays 600 seconds, leaving response/report time below 900.

Verify these system variables:

```text
AUTOGRADER_ENABLED=true
AUTOGRADER_ALLOW_RESET=true
AUTOGRADER_DEFAULT_TARGET=http://127.0.0.1:8080
AUTOGRADER_APPROVED_TARGETS=http://127.0.0.1:8080
AUTOGRADER_RESET_DATABASE=cra_grading
AUTOGRADER_RUN_TIMEOUT_SECONDS=600
VULNERABILITY_SOURCE=fixture
VULNERABILITY_TEST_MODE=true
VULNERABILITY_TEST_DATABASE=cra_grading
```

The three vulnerability settings are **grading-only** settings. Their absence intentionally
returns source-unavailable 503. Test resets are not enabled on the retained DB.
Candidate command equivalent, assuming all existing attachments/secrets/IAM were
verified and remain configured:

```powershell
$systemImage = 'us-central1-docker.pkg.dev/cra-vulnerability-service/cra-phase3/cra-api@sha256:REPLACE_DIGEST'
gcloud run deploy cra-phase3-api --project=cra-vulnerability-service --region=us-central1 --image=$systemImage --no-traffic --tag=phase4-system --timeout=900 --concurrency=8 "--update-env-vars=VULNERABILITY_SOURCE=fixture,VULNERABILITY_TEST_MODE=true,VULNERABILITY_TEST_DATABASE=cra_grading"
```

This intentionally inherits already-verified secret/IAM/Cloud SQL settings. Do not
replace them with guessed names or plaintext values. GET the candidate's actual
tagged URL `/health/ready`, `/test` and `/openapi.json`; verify `reset_ready: true`
and new routes. These are the pre-switch read-only checks; also verify the exact
build digest and grading role/table ownership. Health 200 does not prove 353 tests
passed. If a pre-switch full suite is required, it needs an explicitly approved
maintenance/reset window or a separate isolated environment, never an assumption
that a 0%-traffic tag protects the active database. With current safety guards,
an isolated cloud environment must use its own PostgreSQL instance/connection
with a DB named `cra_grading`; a differently named DB is deliberately refused.

After reviewing those checks, the preserved-data plan and the source-integration
limitation, move 100% system traffic to the verified revision in the coordinated
window. Full hosted testing below requires **separate explicit permission to
reset existing disposable grading data** and no active clients, CLI tests or
independent peer testers. If that permission/window is unavailable, stop after
read-only verification and do not promote based on unrun acceptance tests.

```powershell
gcloud run services update-traffic cra-phase3-api --project=cra-vulnerability-service --region=us-central1 --to-revisions=VERIFIED_SYSTEM_REVISION=100
```

Deploy a no-traffic **cra-phase3-tester** candidate at the same SHA, preserving its
metadata-only secret and approved targets. Keep concurrency 4, timeout 900,
max 1, 1 vCPU/1 GiB. Do not add a domain DATABASE_URL or vulnerability flags.
For normal operation explicitly allow **only Team 2's grading URL**. If the
existing environment contains Team 6, review it and remove that entry outside
a mutually approved reset window; changing the image does not override an
existing `AUTOGRADER_APPROVED_TARGETS` environment variable. Do not contact peers
as a side effect of verifying our deployment.

```powershell
$testerImage = 'us-central1-docker.pkg.dev/cra-vulnerability-service/cra-phase3/cra-tester@sha256:REPLACE_DIGEST'
gcloud run deploy cra-phase3-tester --project=cra-vulnerability-service --region=us-central1 --image=$testerImage --no-traffic --tag=phase4-tester --timeout=900 --concurrency=4
```

After verifying candidate health and one full run against the approved public
system, direct 100% tester traffic to its verified revision. In Console use
Manage traffic, or these commands with **actual revision names from Console**:

Use fresh setup-generated session IDs for both roles and require **353** passing
checks plus the expected runner SHA. Completed historical 157-case reports remain
available by their old IDs and are not proof that the new version ran. The image
includes both test files; it needs no new runtime secret or IAM grant for fixtures.

```powershell
gcloud run services update-traffic cra-phase3-tester --project=cra-vulnerability-service --region=us-central1 --to-revisions=VERIFIED_TESTER_REVISION=100
```

No new Cloud SQL instance, paid feed or queue is needed. Keep current min-instance
policy (0 outside agreed evaluation windows; optional 1 to reduce cold starts
costs extra). Cloud SQL and retained reports still cost storage/runtime; check
the existing budget instead of promising a fixed/free price. OSV snapshots require operator refresh and retained-history storage budgeting;
no Dependency-Track service is required under the new local ADR.

## 5. Hosted evidence, coordination and rollback

With client timeout >=930 seconds, sequentially POST setup/run and GET report on
both public roles. Require 353 passed, 0 failed/errors/skipped, correct AC groups,
recorded SHA/digests/revisions, UTC times and meaningful HTTP evidence. Verify
actual Cloud SQL restart durability in a controlled window, inspect source-error
logs, and capture per-query latency. Update registry/run notes for Phase 4 and
coordinate both directions of Team 6 testing on the frozen Phase 4 fixture set.
The user-reported historical 157/157 result is not a Phase 4 deployed result.

If rollout fails, stop testing/active children first, then direct both services'
traffic back to their recorded **ad42a43** revisions (same update-traffic commands
with old names). Keep grading/report secrets and DBs, leave additive tables in
place, remove new candidate tags after the window. No DROP/TRUNCATE/restore of
retained databases is part of rollback. Old code can still serve Phase 3 routes;
Phase 4 tests must stop until a corrected compatible pair is verified.
If startup/SQL connection fails before promotion, leave both existing revisions
serving traffic and inspect only sanitized candidate logs/secret references/role
permissions. Transactional DDL failure rolls back its changes. If acceptance
fails after approved resets, traffic rollback restores code, **not cleared data**;
preserve any required grading snapshot beforehand using the team's authorized
backup process, or do not authorize that reset. Never restore over `cra_phase3`.

Official references: [Cloud Build execution](https://docs.cloud.google.com/build/docs/running-builds/submit-build-via-cli-api),
[Cloud Run revision/traffic rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration),
[Cloud Run timeouts](https://docs.cloud.google.com/run/docs/configuring/request-timeout).

## 6. OSV production configuration is separate from grading

The paired URL rollout above preserves the resettable grading service in fixture
mode so the full 353-case contract suite can run. It does not turn fixtures into
production OSV. Production mode defaults to `VULNERABILITY_SOURCE=osv`; disable
AUTOGRADER_ENABLED/AUTOGRADER_ALLOW_RESET and VULNERABILITY_TEST_MODE there.
Do not point either mode at retained `cra_phase3`. Decide which service/DB is the
production inventory before an approved cloud change; do not silently repurpose
the registry's grading URL or claim both modes run simultaneously.

For a separately approved OSV runtime use an ordinary domain role on its approved
OSV database with ownership/CREATE on its schema, and a Secret Manager DSN using
the existing Cloud SQL Unix socket. Keep reports in `cra_autograder` under the
report-only role if a report adapter is enabled elsewhere. The OSV runtime must
have no CONNECT/ownership privileges on retained `cra_phase3` or report storage.
Cloud SQL Client plus secret-specific Accessor on its runtime identity suffice;
OSV downloads use public HTTPS without an API key. Do not expose SQL publicly.

Order: approve source/coverage and database choice; review DB permissions; build
the same SHA; initialize additive schema through candidate startup; fetch/review
a suitably scoped snapshot; import with the operator-only CLI from an authorized
runtime with its DSN injected as a secret; inspect provenance/freshness; verify
read-only queries against reviewed versions; then approve traffic promotion. A
Cloud Run service is not an interactive shell. An operator workstation with an
authorized Cloud SQL Auth Proxy, or a separately approved one-off Cloud Run Job
using the same image/SQL attachment/secret identity, can run the import CLI. No
job, scheduler, credentials or additional resources have been created here.

See `osv-snapshots.md` for exact CLI arguments and limits. Max snapshot age defaults
to 7 days; choose refresh frequency and monitoring before production sign-off.
Record the schema/source hashes, actual imported scope and UTC fetch/import time.
One locally downloaded advisory is not sufficient general production coverage.
Rollback code by revision traffic as above. Failed imports preserve the active
generation; successful generations/history remain in SQL. Restoring an earlier
code revision does not undo a snapshot activation or reset, and a stale snapshot
continues to return 503 until an approved refresh. No destructive DB rollback is
part of this plan. Large-feed import time/memory, query latency, operational
refreshing and unsupported ecosystem/GIT coverage remain to be verified.
