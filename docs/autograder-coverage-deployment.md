# Reviewed grading deployment configuration

**Superseded in part by the supplied Cross-team Testing Interface v0.4.2.**
Do not execute the historical secret-provisioning instructions below. The current
system uses public `/test/report` by the tester's session ID; private coverage
controls and the shared coverage secret are retired. The `grading` image,
`AUTOGRADER_COVERAGE_ENABLED=true` on the system, single worker/replica, existing
database bindings and resource limits still apply. See the current
[interface](autograder-interface.md) and [measurements](coverage-measures.md).
This change performs no cloud rollout or public reset.

November 6, 2026. This is a prepared rollout, **not an executed deployment**.
Commit/push/PR approval does not authorize cloud builds, new secrets/IAM,
deployment or public resets. Keep the two registered services and existing SQL
instance/databases. The old Phase 4 rollout's statement that no new secret is
needed applies to fixture CVEs alone; request-driven coverage requires the
additional service secret below.

## Exact profile

The machine-readable source is [deploy/grading-config.json](../deploy/grading-config.json).
It intentionally uses update flags so existing SQL attachments, runtime identities,
DSN secret bindings, probes and public `/test*` access are preserved.

| Setting | System | Tester |
| --- | --- | --- |
| Project / region | `cra-vulnerability-service` / `us-central1` | same |
| Existing service | `cra-phase3-api` | `cra-phase3-tester` |
| Image repository | existing Artifact Registry repo, image `cra-api-grading` | image `cra-tester` |
| Build configuration | `cloudbuild-grading.yaml`, explicit Docker `grading` target | `cloudbuild-tester.yaml` |
| Command | `python -m autograder.grading_server` | `uvicorn app:app --host 0.0.0.0 --port 8080 --timeout-graceful-shutdown 5` |
| CPU / memory | 1 vCPU / 1 GiB | same |
| CPU billing / generation | request-based CPU throttling / gen2 | same |
| Service and revision max instances | 1 / 1 | 1 / 1 |
| Service and revision min instances | 0 / 0 | 0 / 0 |
| Concurrency / request timeout | 8 / 900 seconds | 4 / 900 seconds |
| Child timeout | 600 seconds | 600 seconds |
| Coverage flag | `AUTOGRADER_COVERAGE_ENABLED=true` | same |
| Default, approved and coverage target | `http://127.0.0.1:8080` | `https://cra-phase3-api-456725640364.us-central1.run.app` |
| Domain storage | existing `DATABASE_URL` secret → `cra_grading` | **no domain DSN** |
| Report storage | existing `AUTOGRADER_DATABASE_URL` → `cra_autograder` | same metadata DB |
| Reset authorization | enabled, exact `AUTOGRADER_RESET_DATABASE=cra_grading` | approved disposable target only |
| Vulnerability flags | fixture source, test mode true, test database `cra_grading` | none |
| Coverage authentication | `AUTOGRADER_COVERAGE_TOKEN` → planned `cra-grading-coverage-token:1` | same secret/version |

All exact environment values and entrypoint args are in the JSON file. Do not
add peer origins to coverage targets: peers need their own instrumentation and
must not receive this service key. Public tester callers still need no key;
only service-to-service `/internal/coverage/*` controls require it. Those controls
are not shared pod/grader routes and are excluded from public OpenAPI.

One worker/replica is required for a coherent source collector. Concurrency must
exceed one so a system parent `/test/run` can receive child HTTP requests. During
rollout, pause grading, drain active runs, remove traffic splitting and use one
verified revision at 100%. Stale/misrouted request nonces fail before mutation;
they never create a mixed measurement. Actual hosted routing remains a rollout
verification gate. See [Cloud Run concurrency](https://docs.cloud.google.com/run/docs/about-concurrency).

## Secret and identity preflight, only after cloud-change approval

No usable authenticated Cloud access was established on this workstation.
The new secret/version and existing runtime identities have **not** been checked
or provisioned. Do not guess identities or print existing DSNs/key values.

In the authorized project, inspect both service identities, existing numeric DSN
secret references, Cloud SQL attachment, probes and traffic. Confirm the actual
domain DSN points to `cra_grading`, never retained `cra_phase3`, and reports use
`cra_autograder`. Preserve current image digests/revisions for rollback.

If the planned secret does not already exist, an authorized operator can create
it and add a generated value without printing it or placing it in shell history:

```bash
gcloud secrets create cra-grading-coverage-token --project=cra-vulnerability-service --replication-policy=automatic
openssl rand -hex 32 | gcloud secrets versions add cra-grading-coverage-token --project=cra-vulnerability-service --data-file=-
```

Verify the resulting **numeric version** is enabled. If it differs from planned
version 1, update `coverage_secret_version` before rendering commands. If the
secret exists, inspect its metadata instead of recreating or rotating it blindly.
Grant **secret-specific** `roles/secretmanager.secretAccessor` to each service's
actual existing runtime account, retaining its current Cloud SQL/DSN access:

```bash
cra_system_account="$(gcloud run services describe cra-phase3-api --project=cra-vulnerability-service --region=us-central1 --format='value(spec.template.spec.serviceAccountName)')"
cra_tester_account="$(gcloud run services describe cra-phase3-tester --project=cra-vulnerability-service --region=us-central1 --format='value(spec.template.spec.serviceAccountName)')"
# Stop if either identity is empty; inspect the actual service configuration.
test -n "$cra_system_account" && test -n "$cra_tester_account"
gcloud secrets add-iam-policy-binding cra-grading-coverage-token --project=cra-vulnerability-service --member="serviceAccount:$cra_system_account" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding cra-grading-coverage-token --project=cra-vulnerability-service --member="serviceAccount:$cra_tester_account" --role=roles/secretmanager.secretAccessor
```

These are consequential future instructions, not actions taken in this review.

## Build and render candidate commands

After cloud-build approval, build **the same reviewed source commit** with the
two named Cloud Build files and record actual digests. The grading image has its
own name to avoid overwriting a default production image tag at the same SHA.
The Cloud Build configs build/push images only; they do not deploy.

Render exact candidate commands from actual `sha256:<64 hex>` digests:

```bash
.venv/bin/python scripts/prepare_grading_deployment.py \
  --system-digest "$cra_approved_system_digest" \
  --tester-digest "$cra_approved_tester_digest"
```

The renderer writes `artifacts/deployment-review/system-candidate.sh` and
`tester-candidate.sh`. It does not execute gcloud and refuses tags/placeholders.
No image digest is invented here because approved cloud builds have not run.
Generated commands set the exact image command/args (overriding any old uvicorn
override), update the coverage secret and environment, resource settings, no
traffic and an `autograder-review` tag. Existing DSN secrets/SQL attachments,
probes and IAM remain unchanged. Review the command diff before executing.
See [gcloud update semantics](https://docs.cloud.google.com/sdk/gcloud/reference/run/services/update).

Deploy system candidate first. Before any reset, GET its actual tagged URL's
`/health/ready`, `/test`, `/openapi.json`: require `reset_ready: true`,
`coverage_enabled: true`, `coverage_ready: true`, and setup OpenAPI 201.
Zero traffic does **not** isolate the shared grading DB. Do not POST setup/run
without separately approved exclusive reset permission. Promote one verified
system revision to 100% in a coordinated window, then deploy/verify the tester
candidate at the same source commit against that stable system, and promote it.
Tester discovery has coverage enabled but coverage_ready false (it is a client,
not the source collector). Both registered base URLs remain unchanged.

After explicit reset-test approval, verify fresh independent role sessions:
201 setup/session ID, 200 run/report, 353 passing cases, measured code/component/
model results, correct target/session/role/source hashes and trace digest, report
survival across a normal restart. Confirm real hosted single-replica routing,
memory, latency, secret authorization and metadata persistence. Client timeout
should allow 930 seconds. The grader's own session workflow is still unknown.

Rollback: stop testers/runs, restore their recorded revisions and then the system
revision, with ordinary recorded traffic commands. Old revisions retain their
old entrypoints/settings. Keep additive schema/report records; never restore
over retained data. Code rollback cannot undo an authorized reset. Do not assume
the historical `ad42a43` revision is the currently correct rollback destination.

## Costs and data effects

- No additional Cloud SQL instance, queue, job, coverage service or mounted
  storage is required. The two existing services and report DB are reused.
- Cloud Build minutes and image storage, extra request CPU/memory duration,
  metadata/trace storage and one additional Secret Manager version/accesses
  **can incur charges**. Min instances remain zero; 1 GiB is explicit and may
  increase cost if current deployed memory is lower. Existing settings/billing
  usage are unverified, so this is not a free or fixed-price promise.
  See [Cloud Run pricing](https://cloud.google.com/run/pricing) and
  [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing).
- Candidate deployment/startup does not call reset. Existing initialization may
  check/create missing tables under its normal transaction lock; this fix adds
  no schema migration. Coverage controls read/measure; completed reports write
  metadata JSON. **System setup resets `cra_grading`; both suites reset their
  approved domain target before every case.** Retained `cra_phase3` is guarded
  and must not be selected. Tagged candidates share the live grading DB.
- No cloud builds, charges for provisioned new resources, secrets/IAM changes,
  deployment or public reset tests were initiated in this review.

## Local profile verification

Use a new project and unused loopback ports. Example (choose a fresh suffix):

```bash
export HARNESS_SYSTEM_PORT=18146 HARNESS_TESTER_PORT=18147 HARNESS_SENTINEL_PORT=18152 HARNESS_OSV_PORT=18154
export HARNESS_SYSTEM_URL=http://127.0.0.1:18146 HARNESS_TESTER_URL=http://127.0.0.1:18147
export HARNESS_GRADING_INTEGRATION=1 HARNESS_EVIDENCE_DIR=artifacts/grading-live
docker compose -p cra-phase3-autograder-live-example01 -f tester-service/docker-compose.test.yml -f tester-service/docker-compose.grading.yml up --build -d --wait
.venv/bin/python -m pytest tester-service/tests/test_grading_http.py -q
.venv/bin/python scripts/check_autograder_runtime.py --grading-profile --project cra-phase3-autograder-live-example01 --tester-url http://127.0.0.1:18147 --timeout-port 18148 --unsafe-port 18153 --evidence-dir artifacts/grading-live
docker compose -p cra-phase3-autograder-live-example01 -f tester-service/docker-compose.test.yml stop
```

The local override's obvious test key is never a production credential. It uses
the same grading image and request-driven measurement code as this deployment.
Run ordinary uninstrumented tests in their own disposable project as well;
measurement serialization cannot establish actual concurrent execution behavior.
