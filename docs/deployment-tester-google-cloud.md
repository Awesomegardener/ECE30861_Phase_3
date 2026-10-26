# Deploying the system adapter and separate tester (review before execution)

Nothing in these instructions has created cloud resources or deployed this change.
Follow them only after code review, commit/push/build/deployment approval. Keep
the current service, old revision, secrets and databases available for rollback.
The deadline is October 27, 2026 at 11:59 p.m. Eastern; both URLs must remain
reachable throughout October 28–29. Protocol assumptions are in
`autograder-interface.md`; the original CRA specification stays `docs/openapi.yaml`.

## 1. Preserve data and reuse the existing Cloud SQL instance

Open Google Cloud Console; select the existing project containing
`cra-phase3-api` and the existing PostgreSQL instance. Record the project ID,
instance connection name (`PROJECT:us-central1:INSTANCE`), existing service image,
revision, database secret/version, runtime service account and traffic allocation.
Do not delete instances, databases, users, secrets or backups.

Cloud SQL > existing instance > Databases > Create database:

- `cra_grading`: **empty disposable domain data**, same existing schema initialized
  by the app. Keeping the retained database separate avoids deleting its rows.
- `cra_autograder`: persistent sessions/reports/coordination only.

These are databases inside the existing instance, **not additional instances**.
Use these exact **new** database names. The system adapter refuses setup/run
unless `AUTOGRADER_RESET_DATABASE=cra_grading` and the connected domain database
really is `cra_grading`. It does not accept a retained/course database name as
an alternative. Do not rename a retained database to bypass this restriction.
The original `/api/v1/test/reset` contract remains destructive; only expose the
grading revision to evaluation testers after the database switch is verified.

Create ordinary PostgreSQL login roles using an authorized administrator's SQL
session (Cloud SQL Studio works for these SQL statements). **Do not use the
Console's default Add user flow without explicit custom roles**: built-in users
can automatically receive `cloudsqlsuperuser`, `CREATEDB` and `CREATEROLE`.
Creating roles with SQL as below avoids that automatic membership.
[Cloud SQL role defaults](https://docs.cloud.google.com/sql/docs/postgres/users).

Run once, only for these new roles/databases:

```sql
CREATE ROLE cra_grading_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE cra_harness LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
REVOKE ALL ON DATABASE cra_grading FROM PUBLIC;
REVOKE ALL ON DATABASE cra_autograder FROM PUBLIC;
GRANT CONNECT ON DATABASE cra_grading TO cra_grading_app;
GRANT CONNECT, CREATE ON DATABASE cra_autograder TO cra_harness;
```

Select **cra_grading** in Studio and run:

```sql
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO cra_grading_app;
```

Select **cra_autograder** and run:

```sql
REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

The grading role creates/owns the original CRA tables in `public`; database-level
CREATE alone would not supply schema CREATE on PostgreSQL 15+. The report role
creates/owns `autograder.sessions` and needs no grading access. Neither runtime
role owns a database or has administrative role memberships.

Set separate strong passwords through an authorized interactive `psql` session
using `\password cra_grading_app` and `\password cra_harness` (hidden prompts),
then put the resulting DSNs in Secret Manager below. Use an existing authorized
SQL connection, such as already configured Cloud Shell/Cloud SQL Auth Proxy;
do not open PostgreSQL to the internet for this step. `\password` is a psql
command, not a Studio SQL statement. Do not save filled password-setting SQL,
shell history, plaintext scripts or screenshots. The roles cannot authenticate
with a password until this step is complete. If an existing role has either name,
stop and inspect ownership/memberships rather than altering a teammate's account.

Verify as administrator before deploying:

```sql
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication,
       pg_has_role(oid, 'cloudsqlsuperuser', 'member') AS elevated_member
FROM pg_roles WHERE rolname IN ('cra_grading_app', 'cra_harness');
SELECT has_database_privilege('cra_harness', 'cra_grading', 'CONNECT') AS report_can_grade,
       has_database_privilege('cra_grading_app', 'cra_autograder', 'CONNECT') AS grading_can_report;
```

All listed Boolean results must be false. In `cra_grading`,
`has_schema_privilege('cra_grading_app','public','CREATE')` and USAGE must be true.
After startup, verify the report role owns its `autograder` schema/table. Check
the new accounts have no table privileges or owner-role membership in retained
databases; default PUBLIC CONNECT on an older database does not itself grant
table access. Do not change ACLs or revoke PUBLIC permissions on any existing
database. The tester gets **only the harness DSN**, never the domain DSN.

## 2. Secret Manager and Cloud SQL connection

Use the existing Unix socket approach with psycopg2. Both runtime service accounts
need **Cloud SQL Client** on the project and **Secret Manager Secret Accessor** on
their particular secrets. No Service Account User/Editor/Owner role is needed by
the runtime. The human deployer needs permission to deploy using the selected
runtime identity. Use built-in DB passwords here; Cloud SQL IAM DB authentication
is a separate mechanism and is not silently enabled by Cloud SQL Client.

Secret Manager > Create secret, automatic replication, plain text DSNs:

```text
cra-grading-database-url:
postgresql://cra_grading_app:URL_ENCODED_PASSWORD@/cra_grading?host=/cloudsql/PROJECT:us-central1:INSTANCE

cra-autograder-database-url:
postgresql://cra_harness:URL_ENCODED_PASSWORD@/cra_autograder?host=/cloudsql/PROJECT:us-central1:INSTANCE
```

Replace placeholders and URL-encode special password characters. Do not paste
DSNs into source control, screenshots, registry notes or public evidence. Reference
**numeric secret versions** at deployment for repeatable rollback. No public
PostgreSQL port or authorized public database network is needed: Cloud Run's
Cloud SQL connection attaches the socket. Both services must use the same metadata
database, including during revision transitions, for the shared lock to work.

## 3. Build the two reviewed images in Console

After approved source is on GitHub, open Cloud Build > Triggers. Preserve the
existing region/repository/connection and build-only system trigger. Its config
remains `cloudbuild.yaml`; its Docker context is now the **repository root** so
the system's run endpoint can package the unchanged tester inputs. Direct local
build equivalent: `docker build -f cra-service/Dockerfile .` from the root.
The original Compose command still works because its build context was updated.

Create a second manual/build-only trigger for
`Awesomegardener/ECE30861_Phase_3`, branch `main`, configuration file
`cloudbuild-tester.yaml`. Use the same existing Artifact Registry repository,
`_REGION=us-central1`, `_REPOSITORY=cra-phase3`, and an existing authorized build
service account. It needs Artifact Registry Writer and logging access as with
the current system build; this file does not deploy. Run both triggers on the
exact reviewed commit. Verify success and record image **digests**:

```text
us-central1-docker.pkg.dev/PROJECT/cra-phase3/cra-api:COMMIT_SHA
us-central1-docker.pkg.dev/PROJECT/cra-phase3/cra-tester:COMMIT_SHA
```

Do not choose Cloud Run's source-build flow or its generated Docker build command
unless you explicitly set the root context and the correct Dockerfile. Root
`.dockerignore` excludes local credentials, venvs and generated evidence. Docker
COPY lists include only application/test inputs; no `.git` or artifacts are copied.

## 4. Update the existing system revision

Cloud Run > `cra-phase3-api` > Edit & deploy new revision. Select the new **system**
image digest. Preserve the existing service URL. Set:

| Console setting | Value |
|---|---|
| Region | Existing `us-central1` |
| Container port | `8080`; use image command/arguments |
| Execution environment | Second generation |
| CPU / memory | 1 vCPU / 1 GiB initially |
| Billing | Request-based |
| Request timeout | **900 seconds** |
| Maximum concurrent requests | **8** (self-test must allow other API requests) |
| Minimum / maximum instances | 0 / 1 initially; optionally min 1 during grading |
| Cloud SQL connections | Existing instance connection name |
| Ingress/authentication | All ingress / allow unauthenticated, as registered |
| Runtime identity | Existing or narrowly scoped approved system service account |

Set environment variables (never the secret DSN itself):

```text
AUTOGRADER_ENABLED=true
AUTOGRADER_ALLOW_RESET=true
AUTOGRADER_DEFAULT_TARGET=http://127.0.0.1:8080
AUTOGRADER_APPROVED_TARGETS=http://127.0.0.1:8080
AUTOGRADER_RESET_DATABASE=cra_grading
AUTOGRADER_RUN_TIMEOUT_SECONDS=600
DB_STARTUP_ATTEMPTS=30
```

Variables & secrets > Reference a secret:
`DATABASE_URL` = numeric version of `cra-grading-database-url`;
`AUTOGRADER_DATABASE_URL` = numeric version of `cra-autograder-database-url`.
This intentional revision uses an empty disposable database; the old database is
preserved. Adapter resets accept only the new `cra_grading` database, not an old
course database. System runs use loopback at this container's `PORT`, default
8080. Omitted target settings default to loopback; an explicitly configured
public/remote/wrong-port system target is rejected even if allowlisted. When
using another PORT, omit both system target variables or set them to
`http://127.0.0.1:PORT`.

Configure startup HTTP probe `/health/ready`, port 8080, initial delay 0, period
5 seconds, timeout 3 seconds, failure threshold 36 (180-second budget). Liveness
probe `/health/live`, period 30 seconds, timeout 3, failure threshold 3. Database
outage should not cause a liveness restart loop. Cloud Run probe fields/limits may
vary; retain a supported startup budget within 240 seconds. Do not configure a
liveness probe to call `/test/run` or reset anything.

First deploy a tagged candidate with **both autograder enable/reset flags false**
and the new grading/report secret references. Verify health, image/revision,
the actual database names/role privileges and secrets before enabling controls.
Then deploy the evaluation revision with the flags true and move **100% traffic**
to it during a coordinated window. Verify the public system URL reaches that
revision before deploying/enabling the tester. Avoid split traffic while
switching database secrets; old revisions can still reach the retained database.
Remove old traffic tags that could accidentally be supplied as test targets;
retain the old revision and secrets for deliberate rollback. Do not run any
external tester or the CLI suite until this switch is complete.
On the public system URL, `GET /test` must now return `role: system` and
`reset_ready: true`, based on a read-only database-name/configuration check.
The tester refuses to launch pytest against our known public URL without this
signal, so it cannot run resets against the earlier course revision by mistake.
This is a Team 2-only extension; Team 6 is not required to add it. If the signal
is false, repair the configuration/traffic switch before enabling the tester.

## 5. Create the separate tester service

Cloud Run > Deploy container > use the new `cra-tester` image digest. Service name
**`cra-phase3-tester`**, same project/region. Select port 8080, image entrypoint,
second generation, request-based billing, 1 vCPU / 1 GiB, timeout **900 seconds**,
concurrency **4**, min 0 / max 1. Use a dedicated tester runtime identity with
Cloud SQL Client and accessor permission **only for the report DSN secret**.
Attach the existing Cloud SQL instance and allow unauthenticated ingress. Set:

```text
AUTOGRADER_ENABLED=true
AUTOGRADER_ALLOW_RESET=true
AUTOGRADER_DEFAULT_TARGET=https://cra-phase3-api-456725640364.us-central1.run.app
AUTOGRADER_APPROVED_TARGETS=https://cra-phase3-api-456725640364.us-central1.run.app,http://136.116.160.182:8080
AUTOGRADER_RUN_TIMEOUT_SECONDS=600
```

Reference `AUTOGRADER_DATABASE_URL` from the **same numeric metadata secret
version/database** as the system. Do not set `DATABASE_URL` on the tester. The
allowlist authorizes these origins; enable the tester only after verifying our
system's grading revision serves all traffic. Coordinate Team 6's destructive
reset window before running against them. Do not add arbitrary URLs. The harness
also guards transport in its pytest subprocess: every destination must match
the selected origin and `/api/v1/` path, redirects are never followed (including
same-origin redirects), and environment proxies are ignored. A redirect produces
a real failing/error test result, never a forwarded reset. Direct CLI execution
is unchanged and still needs operator coordination and reset permission.
Use startup probe `/health/ready` and liveness `/health/live` as above. Record the
actual generated tester URL from Console; do not guess it from the system URL.

The 600-second child timeout leaves time for parsing, report persistence and the
900-second request budget. Configure calling clients/proxies for at least 930
seconds. Request timeouts do not by themselves terminate application work, which
is why this implementation also bounds and terminates its child process.
[Cloud Run timeout documentation](https://docs.cloud.google.com/run/docs/configuring/request-timeout).
Scaling settings reduce cost; PostgreSQL locking, rather than instance count,
provides cooperating-run exclusion. System concurrency must support HTTP
self-testing; do not copy a concurrency-1 setting intended for the old service.
[Cloud Run concurrency documentation](https://docs.cloud.google.com/run/docs/configuring/concurrency).

Costs: both services can scale to zero outside grading. One warm instance per
service during the two grading days can reduce cold starts at additional idle
cost. Cloud SQL remains billed while running and is likely the principal fixed
cost; reuse the existing small instance, with no new paid instance or queue. Watch
Billing budgets, Cloud SQL storage/report growth and Cloud Run execution time.
Do not stop the database or services during the announced testing window.

## 6. Verification, registry and rollback

Before destructive verification, confirm `cra_grading` really is disposable and
coordinate an exclusive window. GET both `/`, `/test`, `/health/ready`; check role
and `enabled: true`. For each role POST `/test/setup` (save the ID), POST `/test/run`
with `{"session_id":"SAVED_ID"}`, then GET `/test/report?session_id=SAVED_ID`.
Save actual outcomes, 157 test records, timestamps, image digest, runner SHA,
Cloud Run revision, logs and target URL. Check unknown IDs and unapproved targets.
Restart/revise only the tester and confirm a completed report still exists.
Do not claim hosted verification from local tests. A `fail` report is real test
failure; HTTP 200 alone does not mean acceptance passed. No simultaneous CLI runs.

Registry entries after actual deployment/verification:

| Field | Entry |
|---|---|
| System | `https://cra-phase3-api-456725640364.us-central1.run.app` |
| Tester | **Paste the actual cra-phase3-tester service URL from Console** |
| Intra-pod specification | `https://github.com/Awesomegardener/ECE30861_Phase_3/blob/main/docs/openapi.yaml` |
| Access/run notes | No auth or X-User-Id on `/test*`. POST setup, save session_id, POST synchronous run, GET report with ID. Destructive disposable-target tests; allow up to 900 seconds; use exclusive windows; poll report after a lost response. Original CRA mutations require X-User-Id. |

Optionally include the separate `docs/autograder-openapi.yaml` URL in notes; it
does not replace the original intra-pod specification. The old GitHub Python
blob URL must no longer be registered as the tester base URL.

Rollback: stop initiating runs and let an active run finish (or confirm it was
interrupted). Cloud Run > Revisions > Manage traffic > direct 100% to the prior
known working image/revision. Restore its original database secret/version if
necessary. A prior system without `/test` is not autograder-ready, so communicate
this limitation and fix/redeploy before the deadline. Keep the tester/report DB
and old reports; do not drop databases or delete volumes. For adapter-only
disablement, deploy a revision with `AUTOGRADER_ENABLED=false` and
`AUTOGRADER_ALLOW_RESET=false`; discovery stays available and controls return 503.
