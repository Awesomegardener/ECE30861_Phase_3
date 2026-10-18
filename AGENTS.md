# ECE 30861 CRA Project — Codex Working Instructions

## Mission and current milestone
Build and verify the **Phase 3** increment of our pod's European Union Cyber Resilience Act (CRA) support service. **Do not start a new implementation**: inspect and improve the existing repository, especially `cra-service/`. The authoritative sources are the pod-approved **Phase 2 Section 5 API/OpenAPI contract**, Phase 2 requirements and acceptance criteria, and the Phase 3 assignment. See `docs/project_context.md` for a concise handoff.

## Source-of-truth order
1. The latest instructor-approved, pod-shared OpenAPI/HTTP contract, including schemas and exact errors.
2. The pod's Phase 2 specification (REQ-01–REQ-08, AC-01–AC-10, and Phase 3 milestone in Section 6.1).
3. Phase 3 assignment instructions and instructor clarifications.
4. Existing implementation, tests, and this handoff document.

If these conflict, **point out the conflict and ask before altering any shared contract**. Never silently change public routes, field names, return codes, or semantics. A local implementation fix does not constitute an agreed pod contract change. The original OpenAPI document may not be in this repository yet: request it if absent; do not reconstruct missing details as if authoritative.

## Phase 3 delivery boundary
Implement and validate:
- **REQ-01**: Register releases with product, version, support-end date; calculate support status with UTC reference date, including support through the end of the support-end day.
- **REQ-02**: Accept valid CycloneDX JSON SBOMs for existing releases, associate components and versions with the correct release, and reject malformed/invalid SBOMs with meaningful errors without partial writes.
- Query release components so cross-team tests can inspect ingestion results.
- Contract-defined `/api/v1/test/reset` and `/api/v1/test/clock` behavior for deterministic tests.
- **AC-01, AC-02, AC-03**, including success, negative, and boundary cases.
- A reproducible running service, automated testing, documentation, and a network-accessible deployment usable by podmates.

Later milestones, **not required as finished Phase 3 functionality**: Phase 4 CVE matching, incident cases/deadline logic (REQ-03–REQ-06; AC-04–AC-07); Phase 5 reports, append-only audit log, cross-team completion (REQ-07–REQ-08; AC-08–AC-10). Phase 3 still requires cross-team **readiness** testing and an operation-status list covering the whole agreed API.

## Engineering practices
- Inspect all relevant files and git status first. Present a concise plan before modifying code; wait for explicit approval before substantial edits.
- Favor small, reviewable changes. Do not overwrite teammates' changes; inspect diffs before changing shared files. Never force-push.
- Maintain the existing FastAPI/PostgreSQL/Docker stack unless a clear requirement justifies changing it.
- Validate full request types, required fields, and CycloneDX structural validity; fail cleanly (400/404/etc. as contract specifies). Use transactions to prevent incomplete SBOM replacements.
- Use UTC with deterministic test-clock behavior; do not store a potentially stale `supported` Boolean.
- Avoid secrets in source code or commits. Use environment variables and safe examples. Do not expose PostgreSQL publicly in deployed settings.
- Ensure Docker startup is resilient to DB readiness; verify persistence across normal restarts.
- Make tests runnable against a configurable `BASE_URL` for another team's deployment, not just localhost. Tests must isolate state via reset and assert exact response behavior.
- Add static checks/CI where practical and ensure they run successfully; do not claim a test passed unless you actually ran it. Report tests you could not execute.
- Never run destructive reset operations against another team's service without explicit permission and coordination.
- Do not publish/deploy, spend money, alter production resources, or commit/push changes without explicit user approval.

## Phase 3 review checklist
After changes, report: implemented endpoints; their conformance and known deviations; AC-01/02/03 test names/results; remaining failures; how to run locally; deployment URL/version and operational evidence if available; updated diagrams/docs; risks and incomplete Phase 4/5 scope. Distinguish code presence from tested behavior and hosted availability.
