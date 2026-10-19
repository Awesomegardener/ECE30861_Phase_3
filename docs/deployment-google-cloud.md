# Google Cloud Run and Cloud SQL deployment guide

Prepared October 18, 2026 for `Awesomegardener/ECE30861_Phase_3`, branch `main`.
Use these instructions for explicitly authorized deployments and configuration
review. The original readiness increment created no cloud resources. A later
saved public run against reported SHA `7686edf` has **156 passed / 1 failed**;
[the release/reset investigation](testing.md#release-creation--concurrent-reset-investigation)
documents a locally reproduced/fixed race. That fix is not deployed. No cloud
resource or deployed database was changed during the investigation.
Original local readiness results are in [testing.md](testing.md#google-cloud-deployment-readiness).
Console labels can vary; verify the settings before clicking Create or Deploy.

## What the application now supports

- The Docker command binds Uvicorn to `0.0.0.0:$PORT`, defaulting to 8080. `exec`
  forwards container shutdown signals. Leave Cloud Run command/arguments blank.
- FastAPI lifespan initializes the schema before serving traffic. Independent
  cold starts serialize through PostgreSQL transaction advisory lock `30861003`.
  The lock is released on commit/rollback. Existing `VARCHAR` string fields are
  widened to `TEXT` only when needed; ordinary restarts avoid those ALTER locks.
  No tables/rows are cleared. Unexpected types fail for manual migration review.
- Startup defaults: 30 attempts, 1 second between retries, 180 second total budget;
  connections wait at most 5 seconds, SQL statements at most 5 seconds, lock waits
  at most 3 seconds, capped further by remaining startup time. Transient database
  failures retry; programming/schema errors stop startup. OS/network scheduling
  can add overhead; this is not a hard process-kill timer.
- Health routes need no `X-User-Id` and return `Cache-Control: no-store`:

| GET route | Healthy response | Database unavailable |
|---|---|---|
| `/health/live` | 200 `{"status":"alive"}` | Still 200; no DB query |
| `/health/ready` | 200 `{"status":"ready"}` | 503 `{"status":"unavailable"}` |

Readiness opens a read-only connection and executes `SELECT 1`, with 2 second
connect, 1 second statement and 500 ms lock timeouts. It checks connectivity/query
execution, not every table or database free space. Lifespan handles schema setup.
Health responses contain no connection details and are outside `/api/v1`, hidden
from generated OpenAPI. The shared contract and fixtures are unchanged.

See [PostgreSQL advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS)
and [session timeout settings](https://www.postgresql.org/docs/16/runtime-config-client.html).
Only versions using the same lock cooperate; review any future migration before
mixing old/new revisions. Both local Compose files remain unchanged.

## Proposed small-course configuration and cost

Choose a new project ID and record it as `PROJECT_ID` below; do not type that
placeholder literally. Suggested names/settings:

| Resource | Proposed setting |
|---|---|
| Region everywhere | `us-central1` |
| Artifact Registry | Docker / Standard / regional repository `cra-phase3` |
| Cloud SQL instance | `cra-phase3-pg`, PostgreSQL 16, Enterprise, single zone |
| SQL machine/storage | Shared core `db-f1-micro`, 10 GiB SSD; storage growth cap 20 GiB |
| Database / application user | `cra_phase3` / `cra_app` |
| Runtime / build service accounts | `cra-phase3-runtime` / `cra-phase3-build` |
| Secret | `cra-phase3-database-url`, numeric version pinned in each revision |
| Cloud Run | `cra-phase3-api`, second generation, 1 vCPU, 512 MiB RAM |
| Billing/scaling | Request-based, minimum instances 0, maximum instances 2 |
| Requests | Concurrency 1, timeout 60 seconds, HTTP/1, container port 8080 |

The low concurrency is deliberate: this increment uses synchronous psycopg2
connections without a pool, and tests are sequential. Maximum instances limits
ordinary load, but is not a strict database-connection or spending cap, especially
during revision overlap. Measure latency, memory and connections before raising it.

At the published US shared-core rate, `db-f1-micro` compute is about $7.67 for
730 hours; 10 GiB SSD adds about $1.70/month, roughly **$9.37 base**, excluding
backups, network, taxes and other services. Shared core has no Cloud SQL SLA.
Cloud SQL costs continue while Cloud Run scales to zero. Build, images, secrets,
logs, probes and requests can add charges; do not assume all fit free allowances.
Recheck the Console estimate and [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
before purchase. [Cloud Run pricing](https://cloud.google.com/run/pricing) depends
on region and usage.

## 1. Approve the project and protect billing

1. Review/commit/push this increment only after authorization. Confirm the exact
   new `main` SHA has successful GitHub Actions; the successful baseline
   `f27cfd5a901637525a0bf4dc9dce856fc1fd9903` does not verify these new changes.
2. Console project picker -> **New project**. Select the course billing account
   with its owner's approval; record project ID, project number and owner.
3. **Billing -> Budgets & alerts -> Create budget**: scope this project, suggested
   monthly $20, actual-spend alerts at 50%, 90%, 100% plus a forecast alert. Budget
   notifications do not stop spending. See [budget behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets).
4. **APIs & Services -> Library**: enable Cloud Run Admin, Cloud SQL Admin,
   Secret Manager, Artifact Registry and Cloud Build APIs. Keep the resources
   below in the same project/region.

The person setting up resources needs the corresponding administrative permissions.
A later deployer needs Cloud Run Admin plus Service Account User on the runtime
account and read access to the image. Building/connecting GitHub also needs Cloud
Build permissions and permission to use the build account. If organization policy
blocks a step, ask the project/GitHub administrator; do not use account keys or
grant blanket Editor to bypass it.

## 2. Create the runtime identity and Cloud SQL instance

1. **IAM & Admin -> Service Accounts -> Create service account**:
   ID `cra-phase3-runtime`. Grant **Cloud SQL Client** (`roles/cloudsql.client`)
   in this project. Create no service-account key.
2. **SQL -> Create instance -> PostgreSQL**: ID `cra-phase3-pg`, PostgreSQL 16,
   Enterprise edition. Choose a development/sandbox preset, then explicitly check
   **Customize your instance**: shared core `db-f1-micro`, 10 GiB SSD, single zone,
   `us-central1`. Do not accept a larger/HA preset without reviewing its estimate.
3. **Connections**: enable public IP for the built-in Cloud SQL Auth Proxy path;
   leave **Authorized networks empty**. Do not add `0.0.0.0/0` or publish port
   5432. Use the Google-managed per-instance CA option supported by the selected
   second-generation runtime. Enable automated daily backups, suggested retention
   7 backups; review PITR/storage costs separately. Enable deletion protection.
4. Set a unique administrator password securely. Click **Create instance** only
   after reviewing cost. Wait until running; copy its **Instance connection name**,
   e.g. `PROJECT_ID:us-central1:cra-phase3-pg`.
5. Instance -> **Databases -> Create database**: `cra_phase3`.
6. Instance -> **Users -> Add user account**, built-in authentication: `cra_app`
   and a new long random password (32+ alphanumeric characters simplify DSN entry).
   Store it privately; never put it in Git, screenshots, logs or an image.

The recommended connection is Cloud Run's Cloud SQL attachment and Unix socket.
IAM authorizes the proxy, which encrypts/authenticates the remote connection;
the database user/password separately authorizes PostgreSQL. psycopg2/libpq can
use the socket directly; no new connector package is required. Public IP here
does not authorize arbitrary direct clients. See
[Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
and [authorized-network restrictions](https://docs.cloud.google.com/sql/docs/postgres/authorize-networks).
If a policy prohibits public IP allocation entirely, pause and design private IP
with Direct VPC egress and verified encrypted connectivity. That is a separate
network setup; do not assume attaching a socket automatically selects private IP.

### Limit the database user's privileges

Console-created PostgreSQL users can receive elevated default membership. In
**SQL Studio**, sign in as the administrator, select `cra_phase3`, and run:

```sql
REVOKE cloudsqlsuperuser FROM cra_app;
ALTER ROLE cra_app NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE cra_phase3 TO cra_app;
GRANT USAGE, CREATE ON SCHEMA public TO cra_app;
```

The application creates/owns its three tables and sequences in this new course
database, so it needs schema creation and normal read/write permissions. It does
not need instance administration or creation of other databases. Imported tables
must have compatible ownership before startup can ALTER them; review that
migration explicitly. Do not copy/reset the local database as part of this guide.
See [Cloud SQL user defaults](https://docs.cloud.google.com/sql/docs/postgres/create-manage-users).

## 3. Store DATABASE_URL in Secret Manager

1. **Security -> Secret Manager -> Create secret**: name
   `cra-phase3-database-url`; replication Automatic is sufficient for this course
   unless policy requires a location. Paste one line, substituting actual values:

   ```text
   host=/cloudsql/PROJECT_ID:us-central1:cra-phase3-pg dbname=cra_phase3 user=cra_app password=REPLACE_WITH_PRIVATE_PASSWORD
   ```

2. This is a libpq **keyword DSN**, not an HTTP URL. Use the same new password as
   step 2. For spaces, quotes or backslashes, construct it safely with
   `psycopg2.extensions.make_dsn` privately rather than guessing escaping.
3. Secret -> **Permissions -> Grant access**: principal
   `cra-phase3-runtime@PROJECT_ID.iam.gserviceaccount.com`, role
   **Secret Manager Secret Accessor** on this secret only. Record version `1`
   (or the actual numeric version), not its value.

Keep the administrator password separate from the runtime DSN. Independent
`DB_HOST`, `DB_USER` and `DB_PASSWORD` variables are not read by this application.
No `.env` is uploaded. Runtime identity is attached to Cloud Run; do not set
`GOOGLE_APPLICATION_CREDENTIALS`. Pin a numeric secret version so a redeploy and
rollback have reproducible configuration. See
[Cloud Run secret configuration](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## 4. Build the reviewed source with Cloud Build (build only)

1. **Artifact Registry -> Repositories -> Create repository**: `cra-phase3`,
   Docker, Standard, Region `us-central1`; review retention/storage cost.
2. Create service account `cra-phase3-build`. Grant **Artifact Registry Writer**
   on this repository and **Logs Writer** in the project. Give it no database
   secret access and no Cloud Run deployment role.
3. **Cloud Build -> Repositories -> 2nd gen -> Create host connection**: region
   `us-central1`, provider GitHub. Complete the GitHub App authorization yourself,
   limiting repository access to `Awesomegardener/ECE30861_Phase_3`. Then **Link
   repository**. An administrator may need to approve the installation. See
   [GitHub connection setup](https://docs.cloud.google.com/build/docs/automating-builds/github/connect-repo-github).
4. Give the build identity **Cloud Build Read Only Token Accessor**
   (`roles/cloudbuild.readTokenAccessor`) for the connected source repository,
   using its Permissions panel (or the enclosing connection if repository-level
   permissions are unavailable). This is source access, not DB secret access.
   See [Cloud Build roles](https://docs.cloud.google.com/iam/docs/roles-permissions/cloudbuild).
5. **Cloud Build -> Triggers -> Create trigger**: name `cra-phase3-build-main`,
   region `us-central1`, Event **Manual invocation**, repository generation
   **2nd gen**, select the linked repository, Branch literal `main`.
   Configuration **Cloud Build configuration file (yaml or json)**,
   Location **Repository**, file `cloudbuild.yaml` at repository root. Service
   account: `cra-phase3-build@PROJECT_ID.iam.gserviceaccount.com`.
6. Keep substitutions `_REGION=us-central1`, `_REPOSITORY=cra-phase3`; save.
   Check GitHub CI for the intended main SHA, then **Run trigger** manually.
   Record the resolved full commit from Build details and confirm it is the
   reviewed SHA. If main advanced, review/check that SHA before deployment.
7. In **History**, require success; record build ID, image digest and full-SHA tag:
   `us-central1-docker.pkg.dev/PROJECT_ID/cra-phase3/cra-api:FULL_COMMIT_SHA`.

The supplied config builds using `cra-service/` as context and its Dockerfile,
then publishes the image. It has no deploy step, password or project-specific
credentials. `COMMIT_SHA` comes from the repository trigger. `CLOUD_LOGGING_ONLY`
works with the custom build identity's Logs Writer permission. See
[manual triggers](https://docs.cloud.google.com/build/docs/manually-build-code-source-repos),
[build configuration](https://docs.cloud.google.com/build/docs/build-config-file-schema)
and [custom build identities/logs](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts).
The documented second-generation manual-trigger path is marked Preview; if it
is unavailable in your project, review an alternative build path before proceeding.
This guide does not set up automated deployment on pushes.

## 5. Configure Cloud Run before the first deployment

**Cloud Run -> Services -> Deploy container** (or Create service), select the
Artifact Registry image **by recorded digest**, service `cra-phase3-api`,
region `us-central1`. Expand **Containers, Networking, Security** before Create.

| Console setting | Enter/select |
|---|---|
| Authentication | Allow public access / unauthenticated invocation for coordinated pod tests |
| Ingress | All, giving podmates the HTTPS `run.app` URL |
| Billing | Request-based |
| Scaling | Min 0 / max 2 at service level where available |
| Execution environment | Second generation |
| Container | Port 8080, 1 CPU, 512 MiB; command and arguments blank |
| Requests | Timeout 60 seconds, maximum concurrency 1; HTTP/2 disabled |
| Security -> Service account | `cra-phase3-runtime@PROJECT_ID.iam.gserviceaccount.com` |
| Container settings -> Cloud SQL connections | Add `PROJECT_ID:us-central1:cra-phase3-pg` |
| Variables & Secrets -> Reference a secret | Name `DATABASE_URL`, secret `cra-phase3-database-url`, numeric version `1` |
| Variables & Secrets -> environment variables | `DB_STARTUP_ATTEMPTS=30`, `DB_STARTUP_DELAY_SECONDS=1`, `DB_STARTUP_TIMEOUT_SECONDS=180` |

Cloud Run injects `PORT` from the container port; do not create a separate PORT
variable. No VPC connector, NAT gateway, database volume mount or database port
publication is needed for the recommended proxy path. The socket appears at
`/cloudsql/INSTANCE_CONNECTION_NAME` through the SQL attachment. See the
[Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract).

Public access exposes the agreed reset/clock controls; `X-User-Id` provides
attribution, not authentication. Use **only a dedicated synthetic course-test
database**, coordinate reset windows, and store no sensitive or irreplaceable
data there. Do not silently disable or change those shared endpoints. If the
organization forbids public invocation, agree an authenticated pod testing
arrangement before deploying rather than weakening organization policy.

### Health checks

**Containers -> Health checks -> Add health check**. Use HTTP/1, port 8080,
no custom header, initial delay 0. Replace a default TCP startup check with:

| Type | Path | Period | Timeout | Failure threshold | Success threshold |
|---|---|---|---|---|---|
| Startup | `/health/ready` | 10 s | 5 s | 24 | 1 |
| Liveness | `/health/live` | 30 s | 2 s | 3 | 1 |
| Readiness | `/health/ready` | 30 s | 5 s | 3 | 2 |

The 240 second startup allowance gives the app's 180 second DB budget margin.
Readiness can withdraw traffic during DB failure; liveness avoids restarting a
working process just because PostgreSQL is temporarily down. These probe settings
are recommendations, not measured Cloud Run results. See
[Console probe configuration and behavior](https://docs.cloud.google.com/run/docs/configuring/healthchecks).
Review every setting, then click **Create** only with deployment/spending approval.
Wait for a ready revision; record its name and URL. Do not assume a green build
means the runtime has the right secret, permissions or network path.

## 6. Verify the deployed revision and save report evidence

1. Service -> **Revisions**: record SHA-tagged image/digest, ready revision,
   region, runtime identity, secret version number and traffic allocation.
   Save screenshots excluding secret values. **Logs** should show startup and
   structured request IDs/statuses; inspect failures without copying credentials.
2. Open `https://SERVICE_URL/health/live` and `/health/ready`; require their exact
   200 JSON bodies above. Open `/docs` and `/openapi.json`. Verify HTTPS works from
   outside your machine. Revisit after scale-to-zero to observe a real cold start.
3. With explicit reset permission and Team 6 scheduling, run the **portable HTTP
   suite only** against the new synthetic course database. From this checkout:

   Reserve the service/database for one test run at a time, including across
   teammates, CI jobs and manual tests. The global reset and clock endpoints
   affect every instance sharing that database; concurrency 1 per Cloud Run
   instance does not isolate an entire suite or multiple revisions.

   ```powershell
   $targetUrl = 'https://REPLACE_WITH_SERVICE.run.app'
   $deployedSha = 'REPLACE_WITH_ACTUAL_FULL_DEPLOYED_COMMIT_SHA'
   .\.venv\Scripts\python.exe -X utf8 -B -m pytest cra-service/test_api.py --base-url $targetUrl --allow-reset --capture-http-bodies --tested-commit $deployedSha --evidence-dir artifacts/google-cloud --junitxml=artifacts/google-cloud/results.xml
   .\.venv\Scripts\python.exe -X utf8 -B scripts/check_contract.py --evidence-dir artifacts/google-cloud
   ```

   These **157 HTTP tests reset state**. Do not target the local retained database
   or another team's service without permission. Warm the service with a successful
   readiness request first; record cold-start timing separately from the test
   client's normal request timeout. Internal startup/runtime/SQL-failure scripts
   are for fresh local Docker projects only, not Cloud SQL or another team's host.
4. After automated resets finish, register one synthetic release, upload the
   unchanged 25-component fixture, save release/component responses and UTC
   times. During a coordinated normal revision restart/redeployment, compare
   those same records afterward. No database reset/deletion is part of this
   persistence check. Never simulate a Cloud SQL outage without separate approval.
5. Save CI/build links, SHA, image digest, revision, target URL, health responses,
   JUnit and captured HTTP bundles with source hashes; inspect/redact before
   sharing. The runner accepts an operator-supplied SHA, not independent deployed
   provenance. Review representative AC-03 errors with a teammate. Coordinate
   both cross-team directions and update the class service/test-runner registry.

## 7. Roll back without clearing the database

Before each later rollout, retain the previous healthy revision name, image,
runtime settings, secret version and compatible schema. **Cloud Run -> service ->
Revisions -> Manage traffic**: send 100% to that known healthy revision and save.
Recheck health, release/component reads and logs. The URL stays the same. See
[traffic migration and rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).

Application rollback does not reverse SQL DDL or restore deleted test data. This
increment only adds tables if absent and conditionally widens four string fields;
test compatibility before any future schema change. Retain required image and
secret versions. Password rotation must keep the database and chosen revision's
secret consistent. A first deployment has no previous healthy revision; fix its
configuration or stop rollout. The older baseline lacks these health routes, so
do not blindly reuse new HTTP probe settings with its image. Database backup
restore/migration is a separate approved recovery action, preferably to a new
instance; never delete a database or local volume to repair startup.

## Troubleshooting and remaining gates

| Symptom | Check first |
|---|---|
| Container failed to listen | Image/digest, blank command override, valid injected PORT, startup logs |
| Secret fetch denied | Runtime identity, secret-level Accessor, enabled numeric version |
| Socket/connect failure | SQL attachment, exact instance name/DSN, Cloud SQL Client, instance running, password |
| Schema setup fails | App table ownership/schema CREATE; incompatible types require review, no reset |
| Ready 503, live 200 | DB reachability/connections/query timeout; inspect SQL metrics, avoid liveness restart loops |
| Too many connections/slow requests | Max instances, concurrency, overlapping revisions, SQL CPU/memory; measure before changing size |
| Image build denied | Build account repository Writer, Logs Writer, source token access, trigger SHA/config path |

Outstanding gates: approve project/billing/region/budget and public test access;
review/commit/push this increment and check its CI; execute cloud build/deployment;
verify actual IAM/socket/secret/probe behavior, cold starts and hosted persistence;
complete human AC-03 review and Team 6 coordination. Pod policy questions remain
in [decisions.md](decisions.md). Phase 4/5 features remain out of scope. Assign a
resource owner and cleanup date, but obtain approval before stopping/deleting
cloud resources or backups; this guide performs no cleanup automatically.
