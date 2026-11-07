# Implemented CRA models: Phase 4 local increment

November 1, 2026. Local code, not proof of deployment. [Source ADR](adr-0001-osv-snapshots.md).

November 7 interface correction: [coverage definitions](coverage-measures.md)
use real server statement execution, unavailable component counts pending pod
definitions, and the ten pod acceptance criteria. The earlier architecture/model
transition proposal has been retired; the domain models below remain useful
design documentation.

## Architecture

```mermaid
flowchart LR
 U[Engineer or approved tester] --> A[FastAPI CRA API]
 O[Official OSV HTTPS data] --> F[Operator fetch and review]
 F --> I[Validated CLI atomic import]
 I --> D[(Domain DB: raw OSV generations and inventory)]
 A --> D
 A --> C[UTC deadline calculations on read]
 T -->|Same ID and setup object| H[System HTTP adapter prepares baseline]
 T[Separate tester adapter] --> P
 P[Guarded pytest: 353 cases]
 P -->|Approved grading origin only| A
 A --> W[Source execution since system setup]
 W -->|Public system report by same ID| T
 H --> R[(Separate report DB and execution lock)]
 T --> R
```

Grading explicitly selects fixture source on disposable cra_grading/cra_test;
production defaults to OSV. They are separate modes, never silent fallbacks.
No external network call occurs during matching. No push alerts or complete audit.

## Additive persistence

```mermaid
erDiagram
 INCIDENTS ||--o{ INCIDENT_SUBMISSIONS : records
 INCIDENTS {
  text incident_id PK
  text cve_id "nullable format-only validation"
  timestamptz awareness_at
  text classification
  text rationale
  timestamptz fix_available_at "nullable replaceable"
  text created_by
  text updated_by
  timestamptz created_at
  timestamptz updated_at
 }
 INCIDENT_SUBMISSIONS {
  text submission_id PK
  text incident_id FK
  text stage
  timestamptz submitted_at
  text recorded_by
  timestamptz recorded_at
 }
 OSV_SNAPSHOTS ||--o{ OSV_RECORDS : contains
 OSV_RECORDS ||--o{ OSV_CVES : aliases
 OSV_SNAPSHOTS ||--o| OSV_ACTIVE : selected
 OSV_SNAPSHOTS {
  text snapshot_id PK
  text source_url
  text scope
  text content_sha256
  text upstream_sha256
  text schema_sha256
  timestamptz fetched_at
  timestamptz imported_at
  integer record_count
 }
 OSV_RECORDS {
  text snapshot_id PK,FK
  text record_id PK
  jsonb document
 }
 OSV_CVES {
  text snapshot_id PK,FK
  text cve_id PK
  text record_id PK,FK
 }
 OSV_ACTIVE {
  integer id PK
  text snapshot_id FK
 }
 TEST_VULNERABILITY_SOURCE {
  integer id PK
  text mode
  jsonb records
 }
```

Rows/generations are additive; no snapshot deletion on grading reset. Incident
row locks enforce single new submission per stage without deleting legacy rows.
Statuses are derived, not persisted. Mutable attribution is not audit history.

## Query and deadline behavior

```mermaid
flowchart TD
 Q[Validate CVE format] --> S{Configured source}
 S -->|fixture and grading guards| F[Read replacement fixture dataset]
 S -->|osv| O[Read active provenance and wall-clock freshness]
 O -->|missing stale unsupported or storage failure| E[503 explicit source unavailable]
 O --> K{CVE or alias known?}
 F --> K
 K -->|No| N[404 CVE_UNKNOWN]
 K -->|Yes| M[Versioned package match against inventory]
 M --> G[200 supported and unsupported sets by UTC support date]
```

Fixture PURLs enumerate exact versions ignoring qualifiers/subpaths. OSV explicit
versions/SEMVER/PyPI ranges apply upstream semantics; unsupported comparisons
fail503. Known but unaffected returns empty200. Both sources preserve stored fields.

Mandatory early/notification deadlines are awareness+24h/+72h. Final is fix+14d
or N/A before a fix. Voluntary stays N/A even with a stored fix. Submission <=due
is met, >due overdue; no submission stays pending through equality. Before-awareness
mutations400, N/A submissions400, duplicates409. Fix replacement recalculates
final status. Existing historical duplicate rows use earliest time, with no rewrite.
The shared YAML proposal is separate and awaits review.

## Historical Phase 3 model notes and unchanged release/SBOM views

The October 26 adapter adds a separate `tester-service` FastAPI process and a
shared Team 2 harness package. The tester launches the unchanged HTTP pytest
suite; system setup prepares its supplied ID and system report measures source
execution. Both store session records in `autograder.sessions`, using one shared
PostgreSQL advisory execution lock. In deployment this belongs in a separate
metadata database on the existing Cloud SQL instance; CRA tables above are
unchanged. See [the adapter lifecycle](autograder-interface.md#calls-and-lifecycle).
These are test execution reports, not Phase 5 regulatory reports or audit records.

## Architecture and request flow

```mermaid
flowchart LR
    U[Internal user or pod HTTP test runner] -->|JSON /api/v1| API[FastAPI service]
    API -->|Validate declared 1.4, 1.5 or 1.6 schema offline| V[Packaged CycloneDX validators]
    API -->|Transactional SQL through psycopg2| DB[(PostgreSQL)]
    DB --> PV[Named persistent volume]
    API --> LOG[Request ID, user, status and latency logs]
```

## Persisted data

```mermaid
erDiagram
    RELEASES ||--o{ COMPONENTS : contains
    RELEASES {
        string release_id PK
        text product
        text version
        date support_end_date
    }
    COMPONENTS {
        integer id PK
        string release_id FK
        text name
        text version
        text purl
    }
    TEST_CLOCK {
        integer id PK
        timestamptz now
    }
```

`(product, version)` is unique. Component foreign keys cascade when releases are
reset. The service uses test-clock row 1; otherwise it uses system UTC. There is
no stored support Boolean, separate raw-SBOM table, or audit table. The nullable
component release foreign key in the existing schema is preserved; the API
always associates inserted components with an existing release.

## SBOM replacement behavior

```mermaid
flowchart TD
    A[Check registered release] --> B[Parse JSON]
    B --> C[Validate whole CycloneDX document]
    C --> D[Flatten inventory descendants; require every version]
    D --> E[Begin transaction and lock release row]
    E --> F[Delete prior components and insert replacement]
    F --> G[Commit and close resources]
    B -->|Malformed| R[400 with reason, unchanged inventory]
    C -->|Invalid| R
    D -->|Cannot normalize| R
    F -->|Database failure| RB[Roll back and close resources]
```

With the required user header present, unknown releases return 404 before content
type, JSON or schema validation. Whole-document validation precedes traversal of
root `components` and their inventory descendants at every depth. Every inventory
component requires a string version before any replacement SQL is attempted.
Metadata source/tool subtrees are schema validated but excluded from inventory.
Repeated valid occurrences remain separate rows; identical siblings still fail
CycloneDX `uniqueItems`. No API ordering or persisted parent relationship is added.
The existing schema/transaction handles the flat occurrence list without a schema
migration. Old omitted descendants require resubmitting the original SBOM; no
existing records are rewritten by this change. Approval status for exclusion and
occurrence policies is explicit in `decisions.md`.

The Phase 2 design proposed Dependency-Track and more state entities; this model
removes them from the implemented view rather than implying they are running.
Models were checked against `main.py`, its SQL, and Docker Compose configuration.

## Startup and health in the deployment-readiness increment

```mermaid
flowchart TD
    C[Container start: PORT or 8080] --> F[FastAPI lifespan: bounded DB retry]
    F --> L[Transaction advisory lock 30861003]
    L --> S[Create absent tables; inspect existing string types]
    S --> M[Widen legacy strings only when needed]
    M --> T[Commit and release lock]
    T --> H[Serve HTTP]
    S -->|Unexpected type or SQL failure| R[Rollback and release lock]
    R -->|Transient failure within budget| F
    R -->|Schema error or exhausted budget| X[Fail startup]
    H --> LIVE[GET /health/live: process only]
    H --> READY[GET /health/ready: read-only SELECT 1]
```

The initialization lock coordinates new instances/revisions using the same lock;
it does not replace release-row locks used during SBOM replacement. Health routes
are operational endpoints outside the shared `/api/v1` contract and excluded from
generated OpenAPI. Readiness failure returns generic 503; liveness does not depend
on PostgreSQL. Neither endpoint alters the test clock or persisted application data.

## Planned Google Cloud deployment (not deployed or verified remotely)

```mermaid
flowchart LR
    GH[Reviewed main SHA] --> B[Manual Cloud Build: cloudbuild.yaml]
    B --> AR[Artifact Registry: SHA tag and digest]
    AR -->|Authorized manual deployment| CR[Cloud Run: PORT 8080]
    U[Pod HTTPS test runner] --> CR
    SM[Secret Manager: pinned DATABASE_URL version] --> CR
    CR -->|Cloud SQL attachment: authenticated encrypted proxy| PG[(Cloud SQL PostgreSQL)]
    CR --> CL[Cloud Logging]
```

The runtime account has Cloud SQL Client and secret-specific Accessor. The build
account has separate source/image/log permissions and no DB credentials. No Cloud
Run filesystem persistence is required; PostgreSQL stores releases, components
and clock state. These are proposed cloud resources, not a claim that they exist.
See [the Console guide](deployment-google-cloud.md) for deployment settings and gates.
