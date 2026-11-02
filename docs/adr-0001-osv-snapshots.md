# ADR 0001: Local OSV snapshots for vulnerability matching

Date: November 1, 2026. Implementation selected by Team 2's user; shared pod and
instructor acceptance of the architectural deviation is **not documented**.

Phase 2 sections 7.2/8.1 selected OWASP Dependency-Track, including SBOM forwarding
and project mapping. No Dependency-Track integration was implemented. The supplied
exchange asks whether to switch; Team 2 replied that it was open to OSV. The
current user explicitly requested implementing OSV. That is sufficient authority
for this local implementation, not evidence of finalized Team 6 approval.

Store raw, schema-validated OSV records and provenance in PostgreSQL. An operator
fetches official HTTPS data, reviews its coverage/hash, and atomically imports a
complete generation. Requests match inventory locally against the active
generation. Deterministic `affected_purls` fixtures remain a separate, explicitly
enabled grading source. There is no public import endpoint and no network request
to OSV during an affected-release lookup.

This retains FastAPI, psycopg2, PostgreSQL, Docker and the existing query response
shape. It avoids an additional Dependency-Track server/API key, but transfers
responsibility for refresh, storage growth and matching coverage to the team.
Existing Secret Manager DB credentials and Cloud SQL Client permissions suffice
for an approved import runtime; OSV's public download requires no API key.
Snapshots/history consume database storage. A future scheduled refresh job would
need separate deployment, permissions and budget approval; none was created.

REQ-03/04 and AC-04/05 are **unchanged**: exact affected inventories, support
grouping, precision/recall, latency and explicit source failure remain required.
Changing the component does not approve a scope reduction. Supported matching is
explicit versions, SEMVER ranges and PyPI ECOSYSTEM ranges. Native comparison for
other ecosystems and GIT graph ranges remain incomplete and return 503 when
needed. One real advisory has been verified locally; this does not establish
full ecosystem coverage, a production refresh process or hosted performance.

Deadlines are computed when incidents are retrieved. No push-alert worker, queue,
timer or full Phase 5 audit log is included. Mutable incident attribution fields
are not an immutable record of corrections.

Before production sign-off: obtain the required pod/instructor decision, choose
snapshot ecosystems/refresh SLA, review fixture ground truth jointly, measure
representative snapshot import/query behavior and verify an approved deployment.
See [snapshot operations](osv-snapshots.md) and [deployment](deployment-phase4.md).
