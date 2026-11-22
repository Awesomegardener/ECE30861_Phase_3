# Team 2 design requirements and test mapping (Phase 5)

Version `phase5-1`, November 22, 2026. The machine-readable copy is
[design-requirements.json](design-requirements.json); the hosted tester reads it
to report `coverage.model` when it tests Team 2's own system. A requirement
counts as covered when every mapped test executed in the session, whether it
passed or failed.

| ID | Design requirement | Model | Witness tests |
| --- | --- | --- | --- |
| DR-01 | Support status is computed on every read from `support_end_date` and the UTC (test) clock; no supported flag is stored. | [Persisted data](models.md#persisted-data) | `test_api.py::test_ac01_support_boundary` |
| DR-02 | An SBOM replacement is one transaction; a rejected SBOM leaves the stored inventory unchanged. | [SBOM replacement behavior](models.md#sbom-replacement-behavior) | `test_api.py::test_ac03_invalid_sbom_never_changes_inventory` |
| DR-03 | Nested inventory components are flattened recursively; metadata and tool components are excluded. | [SBOM replacement behavior](models.md#sbom-replacement-behavior) | `test_api.py::test_ac02_nested_inventory_counts_isolation_and_replacement` |
| DR-04 | The vulnerability query distinguishes known-unaffected, unknown CVE and unavailable source. | [Query and deadline behavior](models.md#query-and-deadline-behavior) | `test_phase4_api.py::test_ac05_known_unaffected_unknown_and_outage_are_distinct` |
| DR-05 | Deadline statuses are derived from stored timestamps and the clock at read time; there is no timer component. | [Query and deadline behavior](models.md#query-and-deadline-behavior) | `test_phase4_api.py::test_ac07_unsubmitted_exact_clock_boundaries` |
| DR-06 | Each successful change writes its audit event in the same transaction; failed changes, reads and test controls write none. | [Phase 5 reports and audit log](models.md#phase-5-reports-and-audit-log) | `test_phase5_api.py::test_ac09_failures_reads_and_test_controls_record_nothing` |
| DR-07 | The audit log offers no edit or delete path; the database rejects UPDATE and DELETE on `audit_events`. | [Phase 5 reports and audit log](models.md#phase-5-reports-and-audit-log) | `test_phase5_api.py::test_ac09_audit_entries_cannot_be_edited_or_deleted` (plus the static check `test_phase5_unit.py::test_ac09_no_code_path_updates_or_deletes_audit_events`) |
| DR-08 | Report data is stored per incident and stage and replaced whole; report generation is side-effect free. | [Phase 5 reports and audit log](models.md#phase-5-reports-and-audit-log) | `test_phase5_api.py::test_ac08_put_replaces_the_whole_stage`, `test_phase5_api.py::test_ac08_get_stores_and_audits_nothing_and_uses_the_clock` |
| DR-09 | Test reset clears releases, incidents, report data and the audit log in one transaction. | [Phase 5 reports and audit log](models.md#phase-5-reports-and-audit-log) | `test_phase5_api.py::test_ac08_reset_removes_report_data`, `test_phase5_api.py::test_ac09_reset_clears_the_audit_log` |
| DR-10 | All application data, including audit events, survives a service restart. | [Phase 5 reports and audit log](models.md#phase-5-reports-and-audit-log) | `scripts/check_ac10_restart.py` (two-step; outside the single-session suite) |

DR-10 is checked by the AC-10 restart script, so a single tester session reports
at most 9 of 10 design requirements as covered.
