# Phase 5 implementation: reports and append-only audit log

November 22, 2026. Merged to `main` in PR #4 and PR #5 and deployed to Cloud Run
(see [Deployment](#deployment-november-22-2026)). Not yet run against Team 6.

## What changed

| Area | Change | Requirement / AC |
| --- | --- | --- |
| Contract | `docs/openapi.yaml` 1.0.0 → 1.1.0: PUT report-data returns the generated report; GET reports adds 400; report fields nullable and stage-limited; SBOM accepts `application/vnd.cyclonedx+json`; 405 bodies; audit ordering and actions documented; Phase 4 pending items folded in (409 duplicate submission, 400 malformed CVE, 400 invalid clock, 400 invalid fixture source). | Pod Phase 5 Q1–Q7, Phase 4 answers |
| Reports | New `cra-service/reports.py` and `report_data` table. `PUT /incidents/{id}/report-data/{stage}` replaces the stage's data and returns the report; `GET /incidents/{id}/reports/{stage}` returns supplied fields plus `missing_fields`. | REQ-07, AC-08 |
| Audit log | New `cra-service/audit.py` and `audit_events` table. One event per successful change, written in the same transaction, for the seven agreed actions. `GET /audit-logs` returns oldest first with recording order breaking ties. PATCH/DELETE return 405. Database triggers reject UPDATE/DELETE; TRUNCATE only in `cra_grading`/`cra_test`. | REQ-08, AC-09 |
| SBOM | Accepts `application/vnd.cyclonedx+json` (parameters ignored); missing or other Content-Type stays 400 INVALID_REQUEST. | Pod Phase 5 Q7 |
| Reset | `/api/v1/test/reset` and the adapter reset also clear report data and audit events. | Contract test control |
| Tests | `test_phase5_api.py` (42 HTTP cases: AC-08 30, AC-09 6, Q7 6), `test_phase5_unit.py` (static AC-09 code inspection and report rules), `scripts/check_ac10_restart.py` (two-step AC-10). | AC-08, AC-09, AC-10 |
| Tester | Hosted suite grows from 353 to 395 cases; system coverage now maps AC-08 and AC-09; self-test reports include `coverage.model` from [design-requirements.json](design-requirements.json). | Course testing interface, Phase 5 |
| CI | Runs the AC-10 seed → `docker compose restart api` → verify sequence after pytest. | AC-10 |

## Decisions to confirm with Team 6

- `null` report fields are accepted and listed in `missing_fields` (Team 2's proposal in its Phase 5 response). If Team 6 prefers 400, change `reports.validate_data` and the nullable schema types.
- `entity_type` is `release` for release and SBOM actions and `incident` for incident, fix, submission and report-data actions; submission and report-data events carry `details.stage`.
- `SBOM_REPLACED` is used when the release already had an accepted SBOM (an earlier audit event or stored components); otherwise `SBOM_STORED`.
- PATCH/DELETE on `/audit-logs/{eventId}` return 405 with an Error body and an empty `Allow` header, whether or not the event exists.
- Reset precedence and Team 2-only safety responses (503 for non-disposable reset and disabled fixture source) are not added to the shared contract.

## Local verification (November 22, 2026)

Run on Python 3.11 with a local PostgreSQL 16 `cra_test` database and the API
started with the same environment as `cra-service/docker-compose.test.yml`.
Docker was not available in this environment, so the Compose-based CI jobs were
not run here.

| Check | Result |
| --- | --- |
| `pytest cra-service` (all local tests) | 758 passed |
| Hosted-suite run through `autograder.pytest_guard` (395 cases) | 395 passed; system coverage 9/10 (AC-10 is the two-step script); model coverage 9/10 |
| `scripts/check_ac10_restart.py` seed → process restart → verify | Passed (2 releases, 25 components, 1 incident, 3 reports, 8 audit events identical); a negative control with a post-snapshot change failed as expected |
| Mutation checks (reverse tie order; treat whitespace as present) | Both caught by the new tests |
| Database immutability (`UPDATE`/`DELETE` on `audit_events`; `TRUNCATE` in a non-disposable database) | All refused |
| `pytest tester-service/tests` (non-HTTP) | 121 passed |
| `ruff check`, `ruff format --check`, `mypy`, `scripts/check_contract.py`, `scripts/update_suite_plan.py --check` | Passed; contract reports all 17 operations with routes |

## Run it

```bash
python -m pytest cra-service --allow-reset --base-url http://127.0.0.1:18080
python scripts/check_ac10_restart.py seed --base-url http://127.0.0.1:18080 --allow-reset
# restart the service process without a reset
python scripts/check_ac10_restart.py verify --base-url http://127.0.0.1:18080
```

## Deployment (November 22, 2026)

| Item | Value |
| --- | --- |
| Source commit | `1be34087eeaa29714819a8d3b270c8cfad0be32b` (main after PR #5) |
| System image | `cra-api-grading@sha256:67a094f3353995af5b2f8ff97a0fd2e37cf348ad700788ed1c279913427b77f1` (`cloudbuild-grading.yaml`) |
| Tester image | `cra-tester@sha256:b828661242d0732042672d3af69ca0ea68a7aff1db8364fceacf32ceb7ea5c0f` |
| System revision (100%) | `cra-phase3-api-00012-xaz` |
| Tester revision (100%, `--to-latest`) | `cra-phase3-tester-00007-5gv`: same image, `AUTOGRADER_RUN_TIMEOUT_SECONDS=1800`, request timeout 1900 s |
| Rollback | `cra-phase3-api-00008-yoq` and `cra-phase3-tester-00005-ded` (Phase 4) |

Built with `gcloud builds submit` from Cloud Shell and deployed with `--no-traffic`,
checked read-only on the `phase5-system` tag URL, then promoted. Two problems were
found and fixed on the way:

- The first system build used `cloudbuild.yaml` (no `coverage` package), so the
  grading entrypoint crashed at startup (revision `00010-xal`, never served). The
  grading image must come from `cloudbuild-grading.yaml`.
- The grading entrypoint creates schema only during `/test/setup`, so
  `GET /audit-logs` returned 500 and a peer's direct reset would have failed.
  PR #5 makes `POST /api/v1/test/reset` ensure the schema first.

### Hosted self-test

Session `07556c4e-a9bf-4fac-86f1-e08489a18394`, tester → public system URL:
**395/395 passed** (157 Phase 3, 196 Phase 4, 42 Phase 5), no failures, errors
or skips, in about 20 minutes. System coverage 9/10 (AC-01 to AC-09), model
coverage 9/10 (DR-01 to DR-09), code coverage 354/964 statements over all eight
domain files. A first attempt (session `940ad4ff-d5a0-48ff-972a-521f9c2fcffa`)
hit the old 10-minute tester limit after 222 passing tests; the limit was raised
to 30 minutes, which `deploy/grading-config.json` now records.

## Still open

- AC-10 restart check against the deployed service, after Team 6's run.
- The final cross-team window with Team 6.
- Component coverage remains unavailable: the pod never agreed on a component list.
- Phase 5 report answers (to be drafted from the deployed results).
