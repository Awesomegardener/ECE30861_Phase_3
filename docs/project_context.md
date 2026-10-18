# ECE 30861 CRA Project — Context for Codex

**Handoff date:** October 17, 2026; current implementation update October 18, 2026
**Repository:** https://github.com/Awesomegardener/ECE30861_Phase_3  
**Current emphasis:** Phase 3 milestone (first functioning deployed increment).  
**Status disclaimer:** Sections describing the October 17 snapshot are historical.
Current local verification is summarized below and in `testing.md`; it does not
establish public availability or cross-team execution. Verify the current
branch/commit and dirty state before making changes.

## 0. Current implementation and supplied policy exchange

- Local branch `main`, base commit `0c067d85d7977a32409fa3f552a225424a0b83c1`.
  [GitHub Actions on that main commit](https://github.com/Awesomegardener/ECE30861_Phase_3/actions/runs/39087275607)
  was checked and is successful. The following policy changes were tested as
  working-tree changes before saving, so that baseline CI run does not verify
  them. Check CI for the commit introducing this increment.
- The original shared contract is present at `docs/openapi.yaml`; shared Team 6
  fixtures are present under `fixtures/`. Neither is modified. Source precedence
  remains OpenAPI, Phase 2 specification, assignment, then implementation.
- The user supplied Team 6 questions and Team 2 responses on October 18. Team 2
  accepted missing-header 400/`INVALID_REQUEST`, versions 1.4/1.5/1.6, required
  versions throughout inventory, release-before-body validation, and recursive
  flattening. Metadata/tool exclusion, occurrence retention and wider error-code
  assertions remain Team 2 proposals without a supplied Team 6 acknowledgement.
  See `decisions.md` for the comparison and evidence limits; do not label this a
  newly approved shared OpenAPI revision.
- The validator now uses only packaged 1.4/1.5/1.6 schemas, validates the entire
  document, then walks only root inventory and its descendants. Every versioned
  inventory occurrence is stored/counts; metadata/tool trees are excluded.
  Missing descendant versions reject the whole upload before SQL replacement.
  Existing header/existence ordering and atomic transaction handling are retained.
- CycloneDX `uniqueItems` still rejects identical siblings. Valid repeats across
  branches or with distinct identifiers are preserved. Relaxing schema validity
  for duplicates would need contract reconciliation; it is not implemented.
- Fresh isolated Docker verification on port 18082: baseline **153 passed**;
  expanded suite **264 passed** (157 HTTP, 107 local), no failures/skips.
  Forced final nested SQL INSERT failure preserves 25 old rows and leaves no
  idle transactions. Detailed evidence and preservation checks are in `testing.md`.
- Google Cloud Run plus Cloud SQL PostgreSQL, deploying approved `main` source,
  is the selected hosting plan. No cloud configuration/resources or deployment
  were created. Cloud-specific startup/health/PORT recommendations still need
  review and implementation authorization. Keep both local Compose files.
- The user reports teammate review/approval and has authorized committing/pushing
  this increment directly to `main`. No Phase 4/5 functionality, shared-contract
  revision or deployment is included. Peer-team coordination is with Team 6.

## 1. Product and regulatory context
The EU **Cyber Resilience Act** (Regulation (EU) 2024/2847) imposes cybersecurity and vulnerability-management duties for products with digital elements. The selected project assists manufacturer product security engineers and compliance staff. The pod combined two Phase 1 ideas: release-indexed Software Bill of Materials (SBOM) inventory/vulnerability lookup and internal incident/report-deadline tracking. Its purpose is to track which supported shipped releases contain vulnerable software components and preserve evidence needed for reporting; **humans decide whether an issue is legally reportable, approve and submit regulatory reports, and perform remediation**.

Authoritative regulation: https://eur-lex.europa.eu/eli/reg/2024/2847/oj  
The project focuses on CRA Article 13 / Annex I Part II and Article 14. The student system is compliance *support*, not an automated determination of legal compliance.

## 2. Pod agreement and specification
Phase 2 records a Team 2/Team 6 shared contract, **v1.0**, agreed September 24, 2026 (meeting documented September 26). The specification is described in **Phase 2 Section 5**, including an OpenAPI document originally supplied separately in Drive. That shared document is now in `docs/openapi.yaml`. The Phase 2 PDF includes examples and most public paths but does not reproduce the complete OpenAPI source; use the YAML for exact schemas and status codes.

Broad system scope:
- Included: product/release registration with support end; CycloneDX JSON upload; component lookup; CVE affected-release lookup grouped by support status; explicit unknown/unavailable CVE errors; incident cases with user-supplied awareness times and mandatory/voluntary classification; CRA deadline calculations; staged JSON report data; append-only durable audit trail.
- Excluded: SBOM generation/attestation, automated submissions to ENISA/CSIRTs, legal reportability decisions, maintaining a vulnerability database, and (in this team's selected scope) the one-month final-report path for severe incidents.
- Constraints: internal users, UTC timestamps with trailing `Z`, `X-User-Id` on state-changing application operations, CycloneDX JSON only, mockable/controlled test environment. A release remains supported through its UTC `support_end_date` and becomes unsupported the following UTC day.

The team's Phase 2 design proposed a REST service, PostgreSQL for authoritative data/persistent timestamps, Docker Compose, and OWASP Dependency-Track for eventual vulnerability matching. Reuse Dependency-Track is **not** a prerequisite for Phase 3 release/SBOM storage.

## 3. Requirements and acceptance criteria overview
| ID | Requirement (paraphrased from Phase 2) | Milestone |
|---|---|---|
| REQ-01 | Register release (product/version/support end); calculate support status | Phase 3 |
| REQ-02 | Validate and store CycloneDX JSON SBOM and per-release components; reject invalid with reason | Phase 3 |
| REQ-03 | CVE query returns all affected releases grouped by support status; seeded-dataset recall | Phase 4 |
| REQ-04 | Unknown CVE or unreachable vulnerability source is explicit, not an empty result | Phase 4 |
| REQ-05 | Record incident awareness UTC time, user, classification, rationale | Phase 4 |
| REQ-06 | Mandatory incident: awareness+24h, awareness+72h, fix-available+14d; pending/met/overdue | Phase 4 |
| REQ-07 | Output stage-specific report JSON with `missing_fields` | Phase 5 |
| REQ-08 | Time/user-stamped immutable audit history and data persistence across restarts | Phase 5 |

**Phase 3 acceptance criteria:**
- **AC-01 / REQ-01**: At a fixed UTC clock, register past, current-boundary, future, and missing-support-end releases. Current and future must be supported through end of boundary day; past unsupported; incomplete request rejected with no record saved.
- **AC-02 / REQ-02**: Register two releases; upload a valid **25-component** CycloneDX JSON SBOM to the first. All 25 component names/versions must be retrievable under that release and none under the second.
- **AC-03 / REQ-02**: Reject **malformed JSON**, CycloneDX JSON missing mandatory fields, **plain text**, and SBOM for an unknown release; store zero components on each rejected upload; error messages identify reasons.

Future AC-04–AC-10 test CVE lookup accuracy/error paths, incident validation/deadline boundaries, JSON report schemas, audit append-only behavior, and restart durability. They should be listed in the Phase 3 API operation-status report even though future endpoint functionality may be absent.

## 4. Phase 3 exact promised milestone (Phase 2 Section 6.1)
- **Capability:** release registration, CycloneDX SBOM ingestion, baseline testability.
- **Artifacts:** database schemas; `/releases`, `/releases/{releaseId}/sbom`, `/test/reset`, `/test/clock` endpoints (and component retrieval to support the published API contract).
- **Risk reduced:** nested CycloneDX parsing and lossless normalization into persisted component records.
- **Demonstration:** deploy to a network-accessible host, register a release, upload and persist the pod's shared SBOM.
- **Automated validation:** AC-01, AC-02, AC-03.

Phase 4: CVE affected-release lookup, simulated vulnerability-source failures, incident cases, deadline math (AC-04–07).  
Phase 5: stage reports, immutable audit logging, persistence proof, final cross-team suite (AC-08–10).

## 5. Common HTTP contract essentials (check exact OpenAPI)
Available Phase 2 examples include these operations:

| Method/path | Purpose |
|---|---|
| `POST /api/v1/releases` | Create release; `product`, `version`, `support_end_date`; 201 and release ID/support status |
| `GET /api/v1/releases/{releaseId}` | Retrieve release (currently implemented; verify contract listing) |
| `PUT /api/v1/releases/{releaseId}/sbom` | Store CycloneDX JSON for release |
| `GET /api/v1/releases/{releaseId}/components` | Retrieve release component array |
| `GET /api/v1/vulnerabilities/{cveId}/affected-releases` | Phase 4 affected releases |
| `POST /api/v1/incidents` | Phase 4 awareness/classification case |
| `PATCH /api/v1/incidents/{incidentId}` | Phase 4 fix-available time |
| `POST /api/v1/incidents/{incidentId}/submissions` | Phase 4 record stage submission |
| `PUT /api/v1/incidents/{incidentId}/report-data/{stage}` | Phase 5 stage data storage |
| `GET /api/v1/incidents/{incidentId}/reports/{stage}` | Phase 5 generated report |
| `GET /api/v1/audit-logs` | Phase 5 append-only log retrieval |
| `POST /api/v1/test/reset` | Reset shared fixtures/test state |
| `PUT /api/v1/test/clock` | Set deterministic UTC test clock |

These are a **handoff summary, not a replacement for OpenAPI**. Validate required schemas, success codes, errors, paths, and test reset/clock semantics from the shared contract. Phase 2 specifies test operations for repeatability and no authentication for the common test interface; mutation attribution uses `X-User-Id` but is not itself authentication.

## 6. Historical October 17 repository snapshot (superseded by section 0)
Repository: https://github.com/Awesomegardener/ECE30861_Phase_3  
Reviewed uploaded commit: `99147b3bf9e2f1c02f54bd017a126b66e776fef3` on `main` (October 17, 2026). Clone/fetch before making assumptions.

Files observed:
```
cra-service/
  main.py
  test_api.py
  requirements.txt
  Dockerfile
  docker-compose.yml
  __pycache__/test_api.cpython-313-pytest-9.0.2.pyc  # should not be tracked
README.md    # currently minimal placeholder
```

**Implementation found:** FastAPI (`main.py`) using psycopg2 + PostgreSQL tables (`releases`, `components`, `test_clock`), release create/get, SBOM upload, component get, reset/clock endpoints. Docker Compose creates PostgreSQL and the API; a Python test file uses `requests` for simple HTTP checks. This is a starting point, not verified completion.

**Prioritized findings for Codex to independently confirm:**
1. **DB readiness at startup:** `init_db()` runs at module import; Compose `depends_on` does not wait until PostgreSQL accepts connections. Use health checks/retries or lifecycle initialization.
2. **SBOM validation incomplete:** only `bomFormat` and presence of `components` checked, without complete CycloneDX-required fields or robust types. Unexpected data types may raise 500s. Reject invalid content explicitly, atomically, without destroying prior SBOM.
3. **Insufficient AC coverage:** tests check only two support dates (not boundary/missing); a single SBOM component (not 25 or cross-release isolation); one invalid SBOM (not four failure classes).
4. **Test runner tied to localhost:** `BASE_URL = "http://localhost:8080/api/v1"`. Read from environment/CLI instead so it can target podmate services.
5. **Release strings accept empty text:** require nonempty `product`/`version` and contract-consistent validation.
6. **Database cleanup and rollback:** handle exceptions so cursors/connections are closed and all writes are transactional.
7. **Deployment/CI/doc gaps:** Docker file is not proof of remote deployment; no CI workflow was found in reviewed commit; README was placeholder. Need hosting URL, commit/version mapping, test results, static checks, and operations documentation.
8. **Security/configuration:** Compose has development database password embedded and publishes PostgreSQL port. Replace with environment-based settings; do not expose DB port in production. Remove tracked `__pycache__` from git and add `.gitignore`.

**Not yet checked:** running code, deployment URL, instructor OpenAPI conformance suite, cloud service logs, persistence under restart, Team 2 cross-test results. Do not state those passed without evidence.

## 7. Phase 3 reporting/deliverables beyond implementation
The Phase 3 assignment asks for:
1. Delivered increment and REQ/AC completion statuses; comparison to Phase 2 Section 6.1.
2. Network-accessible deployed service information, repository commit/tag, operational evidence (logs/metrics), registry entry, and current team documentation.
3. **One line for every contract operation**, whether implemented or not, with success/error conformance; contract changes and pod approval (if any).
4. Test runner/base URL, AC-to-test mapping, failure-path tests, regression/static CI, and actual test-run counts/failures.
5. Updated Phase 2 models reflecting *implemented* architecture (not imagined components), with consistency explanation.
6. **Cross-team readiness:** run your suite on Team 6 and have their suite run on yours, record execution/results and one specification ambiguity found with resolution plan; Phase 3 emphasizes connectivity/well-formed reports, and cross-team outcomes begin counting in Phase 4.
7. Remaining scope/limitations (`LIM` severity/workaround/target phase), Phase 4 milestone adjustments, and updated risks.
8. **Per-teammate** factual GenAI use: what was delegated, verification, an actual error/correction, and agentic principles.
9. Sources for regulation, tools/frameworks/services actually used.

The phase also requires the class deployment registry entry to identify **both web service and automated test runner**. Do not invent a deployment or cross-team test result in the report.

## 8. Remaining work after this increment
1. Save the reviewed policy implementation under the user's explicit commit/push
   authorization, then check CI for the resulting SHA and retain its evidence.
2. Obtain Team 6 acknowledgement of the outstanding proposals in `decisions.md`;
   reconcile any shared-contract changes through the pod before editing YAML.
3. Review the Google Cloud plan, project/billing/region and startup/health changes.
   Deploy only after explicit authorization, using a separate course-test database.
4. Run the HTTP suite against the deployed URL with coordinated reset permission;
   record source SHA, image/revision, persistence, logs and both testing directions.
5. Update the class registry, implemented models and Phase 3 report with factual
   test results, human AC-03 inspection and each teammate's own GenAI account.
