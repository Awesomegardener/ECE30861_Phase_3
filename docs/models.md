# Implemented Phase 3 models

These models describe actual components. Dependency-Track, incident management,
reports and audit storage are absent from this increment.

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
