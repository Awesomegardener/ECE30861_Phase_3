# Autograder review and rollout handoff

**Historical November 6 review.** Its unknown-request/schema assumptions and
private measurement protocol are superseded by the supplied full course prose
and exact `target_url` request. Use the [current interface](autograder-interface.md)
and [coverage definitions](coverage-measures.md) for this branch.

November 6, 2026. Branch `fix/phase3-autograder`, based on `125e927`.
The user authorized commit/push/PR during publication review. Cloud builds,
secret/IAM changes, deployment, registry edits and public reset tests were not
executed or authorized by that publishing instruction.

## Confirmed fixes and review corrections

- Both roles return **201** with `session_id` on successful setup, in actual
  responses, generated OpenAPI and the provisional adapter specification.
  Run/report remain **200**. Errors keep their existing status behavior.
- Unknown-field diagnostics include bounded safe names/types and accepted fields,
  without values, nested contents, credentials or control characters. Validation
  remains strict: no guessed aliases, ignored target-selecting inputs or relaxed
  target/reset authorization.
- Review found the original collector was local-only. It was replaced by the
  authenticated request-driven grading path described in [coverage measures](coverage-measures.md).
  Both role runs now obtain genuine target execution before returning and save
  measurements plus a hashed compressed trace in existing durable reports.
- Per-run nonces, instance/role/session binding, collection-before-worker startup,
  serialized tracer contexts, separate snapshot reporting, physical/logical line
  translation, stale-token refusal, timeout/abort and abandoned-parent recovery
  address measurement mixing. Redundant region/context output was removed from
  the artifact to keep Cloud Run memory and report storage practical.
- The regular production image and original domain contract/fixtures/Phase 4
  implementation remain intact. Two Phase 3 tests gained before/after assertions
  for duplicate preservation and support expiry. The suite still has 353 cases.

## Still unresolved

**The original unknown-field 400 is not fixed.** The grader request is unavailable.
Both JSON/query fields reach the same validator, which accepts only `session_id`,
`target_base_url`, `now`. Generic old errors contain no rejected field names.
No request body was reconstructed. Authenticated Cloud Logging was inaccessible;
see [read-only deployment/registry inspection](deployment-inspection-2026-11-06.md).

Staff still needs to confirm request fields, tester/system session linkage and
coverage field names/definitions. Code/component/model measures are explicitly
Team 2 proposals; HTTP operation observations remain separate. No full grader
compatibility, score, successful regrade or new hosted deployment is claimed.

The registered URLs/spec/access notes were read without public mutations. Both
services were reachable, but deployed OpenAPI still advertised setup 200. The
latest readable tester report was 341/353 against **Team 6**, with no coverage;
it does not refute the registry's historical 353/353 own-system claim. System
latest-report lookup returned 404, not proof about an existing valid session ID.

## Validation

The final review passed **131** offline tester regressions, **348** CRA unit
regressions, **8** ordinary HTTP checks, **4** request-driven grading checks and
**6** grading runtime checks. Both ordinary and measured role children run all 353 cases:
AC-01/02/03 = 63/5/89; AC-04/05/06/07 = 10/11/62/113. Representative tests include
`test_ac01_support_boundary`, `test_ac02_shared_25_components_are_isolated`,
`test_ac03_invalid_sbom_never_changes_inventory` and nested atomic replacement.

Each measured role currently records 245/796 statements, 75/240 branches, 8/10
architectural components and 16/18 proposed model transitions. OSV components and
attributed rollback/OSV activation remain gaps; Phase 5 remains deferred.
Ruff lint/format, mypy, original contract/fixture checks and provisional OpenAPI
validation are required. Local results are not a remote Actions run.

Evidence: `artifacts/grading-live/` contains measured reports, HTTP JUnit, runtime
results and service logs. `artifacts/autograder/review-*-results.xml` contains
unit/ordinary HTTP evidence. Earlier failed prototypes and historical local-only
evidence are retained in ignored artifacts, not claimed as final successes.

## Reproduce and deploy

Use Python 3.11, `.venv`, Docker Compose v2. Install
`cra-service/requirements-dev.txt`. Run offline tests excluding both opt-in HTTP
modules. Start a fresh disposable base Compose project for ordinary tests; use
the `docker-compose.grading.yml` override for measured tests. Exact commands,
Cloud Run configuration, new secret requirements, cost/reset effects and ordered
rollout are in [the deployment guide](autograder-coverage-deployment.md).

CI now exercises both profiles and retains their artifacts. GitHub publication
does not authorize a deployment or a public reset. Preserve registered URLs,
existing SQL/DSN references and rollback revisions; no DB schema migration is
required by this fix. Deployment itself does not reset domain data. System setup
and both role suites **do reset** the shared disposable grading database.
