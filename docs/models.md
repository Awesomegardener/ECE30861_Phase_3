# Implemented Phase 3 models

These models describe actual components. Dependency-Track, incident management,
reports and audit storage are absent from this increment.

## Architecture and request flow

```mermaid
flowchart LR
    U[Internal user or pod HTTP test runner] -->|JSON /api/v1| API[FastAPI service]
    API -->|Validate declared CycloneDX schema offline| V[Packaged CycloneDX validators]
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
    C --> D[Check current normalization requirements]
    D --> E[Begin transaction and lock release row]
    E --> F[Delete prior components and insert replacement]
    F --> G[Commit and close resources]
    B -->|Malformed| R[400 with reason, unchanged inventory]
    C -->|Invalid| R
    D -->|Cannot normalize| R
    F -->|Database failure| RB[Roll back and close resources]
```

Unknown releases return 404. Metadata source/tool components are not inventory.
Nested children are validated but not yet normalized into stored rows; that
remaining Phase 3 risk is explicit in `decisions.md`.

The Phase 2 design proposed Dependency-Track and more state entities; this model
removes them from the implemented view rather than implying they are running.
Models were checked against `main.py`, its SQL, and Docker Compose configuration.
