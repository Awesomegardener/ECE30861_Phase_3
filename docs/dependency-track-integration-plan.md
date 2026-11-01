> Historical review/proposal, superseded November 1, 2026 by [the pod update](phase4-pod-update.md) and [OSV ADR](adr-0001-osv-snapshots.md). Counts and source limitations below describe the earlier implementation, not the current code.

# Dependency-Track integration: gap and proposed implementation

November 1, 2026. **Design proposal only; no resources, integration, keys or
production requests have been created by this review.** Obtain cost/deployment
approval before execution. Preserve both existing Cloud Run URLs and domain/
report databases; do not initialize or migrate retained `cra_phase3`.

## What is implemented and what Phase 4 can claim

The shared OpenAPI allows a deterministic test source without fixing the
production implementation. Current `phase4.py` reads `cve_id/affected_purls`
records from the opt-in grading DB, matches exact stored PURLs and groups
releases by UTC support status. It distinguishes known-unaffected (200), unknown
(404 CVE_UNKNOWN) and simulated unavailable (503 VULNERABILITY_SOURCE_UNREACHABLE).
Outside enabled disposable test mode, it always returns source-unavailable 503.

No Dependency-Track client, project mapping, raw-BOM forwarding, analysis wait,
feed mirror, credentials, live matching, freshness monitoring or source worker
exists. A passing fixture suite proves neither live matching nor a live source
outage path. The synthetic five-CVE oracle is not the absent pod manifest.

Phase 2 section 6.2 names querying, fault injection and deadlines; those public
behaviors can be tested deterministically. But sections 2.2, 7.2 and 8.1 explicitly
select Dependency-Track, and Risk 1 requires proving matching/source reliability
before Phase 4. Therefore the current work is **partial against the full Phase 2
delivery plan**, even with passing local HTTP tests. Do not claim complete Phase 4
production matching without this integration or a documented, appropriately
approved plan change. The OSV fallback mentioned in Risk 1 was not implemented
or approved here. Confirm the interpretation with Team 6/instructor; the shared
API's freedom of implementation is not evidence that the team delivered its own
selected integration.

Recommendation: resolve that delivery decision **before promoting this as a
complete Phase 4 production increment**. Committing reviewed code, or a separately
approved grading-only deployment explicitly labeled fixture-only, need not be
blocked by building a source that has not yet been authorized or funded.

## Proposed infrastructure (reuse the existing application stack)

Keep FastAPI + psycopg2 on Cloud Run and its existing Cloud SQL storage. Add one
always-running Compute Engine VM in `us-central1` for Dependency-Track API server,
its own PostgreSQL container, optional administration frontend, and a sync worker.
Use a dedicated persistent disk/volume with an approved snapshot/backup policy.
Do not share CRA grading/report tables or the retained database with the scanner.
The proposed additional scanner database stays on this VM, avoiding another
Cloud SQL instance and avoiding mirror load on the current small Cloud SQL tier.
Validate its recovery/storage capacity before treating it as production reliable.

Dependency-Track documents a minimum 2 cores/2 GB and recommended 4 cores/8 GB
for its API server [1]. For a small measured trial, `e2-standard-2` (2 cores/8 GiB)
has room for more than the API minimum but still needs benchmarking with the
database/worker. `e2-standard-4` offers more CPU/headroom. Neither choice is an
availability guarantee or automatic approval to spend money. Do not squeeze a
Java scanner/database into the existing 1-CPU/1-GiB request-billed CRA container.

Pin a reviewed Dependency-Track image version and digest (4.14.6 is documented
as released October 25, 2026 [2]); check its actual API schema before coding.
Restrict the VM's scanner port to private VPC access, with an HTTPS reverse proxy
and certificate trusted by the CRA client. Keep database ports on the Docker
network/loopback; administration uses authorized IAP/SSH forwarding, not a public
scanner UI. A public VM address can be used for outbound mirror downloads with
inbound ports blocked; an external-IP-free VM may require Cloud NAT, with extra
cost. Review actual VPC/subnet/firewall/DNS availability first.

Configure the **system** Cloud Run service for Direct VPC egress to the private
scanner endpoint; the tester needs no scanner access. Direct VPC egress avoids a
Serverless VPC Access connector but has its own subnet capacity and cold-start
considerations [3]. This changes networking and must be reviewed/deployed as a
new revision, never applied to the active service during local work.

## Authentication, secrets and permissions

Dependency-Track API calls use a team API key and its version's documented
permissions; the backend exposes its actual OpenAPI at `/api/openapi.json` [4].
Create separate read/query and ingestion teams/keys with the smallest necessary
permissions. Candidate permissions to validate against the pinned operation
schemas: query VIEW_PORTFOLIO/VIEW_VULNERABILITY; ingestion BOM_UPLOAD and project
creation/management permissions only as needed [5]. Never give the CRA runtime
the scanner's administration/system-configuration key.

Store keys and scanner DB credentials in Secret Manager, pin numeric versions,
and grant secret-specific Accessor only to the consuming service accounts. The
system gets the read key and a mounted trusted CA certificate bundle; do not use
`verify=False`. The VM ingestion worker gets only its upload key and a separate
least-privilege CRA sync-role DSN. VM Cloud SQL Auth Proxy access for that worker
requires Cloud SQL Client plus the SQL role's explicit table grants; it grants
no permission to retained data, resets or incident/report tables. Use attached
Google identities, not downloaded service-account JSON keys.

Deployer permissions must cover the VM/disk, VPC/subnet/firewall, selected runtime
identities and secret references. This does not justify broad Owner/Editor grants
to runtime accounts. NVD/analyzer credentials, if required for the chosen mirror
configuration, are separate secrets subject to provider terms/rate limits; obtain
them explicitly rather than assuming free unlimited upstream access.

## Proposed code and data changes

1. Add `vulnerability_sources.py` with an explicit fixture/Dependency-Track source
   interface and operator-selected mode. Keep test injection confined to the
   actual disposable grading DB. Source failures must never fall back to fixture
   or empty results in production.
2. Store release-to-project UUID mapping and the acknowledged SBOM revision/hash.
   Preserve raw validated SBOM JSON in a new table so existing accepted uploads
   can be forwarded accurately. Existing Phase 3 components alone omit metadata
   and parent relationships and are not a lossless raw SBOM replacement. Obtain
   original documents for backfill; never fabricate them or delete old data.
3. Add a transactional PostgreSQL outbox beside atomic local SBOM replacement.
   Queue/retry scanner synchronization without changing existing 200/400/404
   SBOM semantics or coupling a successful local commit to external uptime.
   A durable worker on the always-on VM reads only approved sync tables through
   the proxy, uploads the matching project/version BOM and records acknowledged
   revision. Do not rely on an unawaited Cloud Run background task after response.
4. Inspect the pinned scanner OpenAPI, then implement actual known-CVE lookup,
   pagination and affected project/component findings. Include alias handling
   where the source uses another advisory identifier. Translate scanner findings
   back to current local release/component occurrences, keeping existing UTC
   grouping and avoiding duplicate release rows. Do not invent undocumented
   scanner API paths in the implementation plan.
5. Treat BOM acceptance/processing as asynchronous; verify ingestion **and
   completed analysis**, not just an accepted token [6]. Fence results by the
   current local SBOM revision. A removed component or failed replacement must
   not leave stale positives, and unsynchronized inventory must not return a
   misleading empty result. Agree the temporary-unavailable semantics with the
   pod before implementing lag handling; shared YAML currently only specifies
   the source-unreachable 503.
6. Use a fixed operator-configured HTTPS origin, verified certificates, no
   redirects, scrubbed headers/logs, bounded response sizes/pagination and one
   overall query budget below 10 seconds. Upstream auth/malformed response/
   timeout/connection failures are unavailable, not CVE_UNKNOWN. Return 404 only
   from a successful authoritative lookup in an initialized configured mirror.
   Mirror warm-up/freshness and sync backlog need explicit operational status;
   the source being reachable alone does not prove its inventory is current.

Likely affected files: `cra-service/vulnerability_sources.py`, a durable sync
worker, `phase4.py`, startup schema, SBOM transaction/outbox integration, pinned
dependencies if needed, VM Compose/configuration, source integration tests,
deployment/IAM/secrets guides and implemented models. These are **future work**,
not files silently added by the final review. Keep shared contract/fixtures
unchanged unless a documented pod decision requires their revision.

## Cost and deployment order

Google's Iowa on-demand table lists `e2-standard-2` at $0.06701142/hour and
`e2-standard-4` at $0.13402284/hour when checked November 1, 2026 [7]. VM compute
alone is approximately **$48.92/$97.84 for 730 hours**, or **$11.26/$22.52 for
168 hours**. Disks, snapshots, IPv4, network, logs/secrets and any NAT are extra;
existing Cloud SQL/Run charges continue. Credits/discounts/taxes are excluded.
Use a budget and approved evaluation window; these figures are estimates, not
an invoice quote or a commitment to keep resources running indefinitely.

After approval: build/test the client and worker locally with a pinned real
scanner; provision the private scanner and its own persistent database; warm and
validate mirrors; configure least-privilege keys; backfill originals and verify
revision synchronization; then deploy a no-traffic CRA candidate with source
secrets/networking. Apply the safe staged rollout in `deployment-phase4.md`.
Update the tester from the **same reviewed SHA**, preserving both service URLs.
Retain the old revision and compatible secrets for code rollback, but never
restore retained CRA data as part of a scanner rollback.

## Required integration evidence before completion

- Five agreed CVEs: 100% precision/recall, exact version/component/release fields,
  current support grouping and every query <10 seconds against the pod manifest.
- Real production-client path with fixture mode **off**: known-empty 200,
  confirmed-unknown 404, actual scanner outage/timeout/auth/malformed-response 503,
  each error scenario <15 seconds. A fixture-only pass is insufficient.
- BOM accepted but not analyzed; duplicate/retried jobs; scanner restart; source
  mirror warm-up; concurrent replacement with an older upload finishing last;
  pagination; patched/no-PURL/nested inventory; no stale or partial match results.
- All original 157 and expanded 311 HTTP checks still pass; separate end-to-end
  source tests prove the fixture override is not hiding an integration failure.
- SQL outbox rollback/retry, least-privilege role/key tests, TLS verification,
  secret redaction, scanner DB backup/restore and both cross-team directions.
- Actual deployed SHA/digests, source/mirror version, logs/latency, backlog and
  tested costs; no invented hosted or peer results.

References (official sources, accessed November 1, 2026):

[1] https://docs.dependencytrack.org/getting-started/deploy-docker/

[2] https://docs.dependencytrack.org/changelog/

[3] https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc

[4] https://docs.dependencytrack.org/integrations/rest-api/

[5] https://docs.dependencytrack.org/administration/users-and-permissions/

[6] https://docs.dependencytrack.org/2024/05/07/v4.11.0/

[7] https://cloud.google.com/products/compute/pricing/general-purpose?hl=en
