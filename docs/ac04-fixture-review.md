# AC-04 fixture review worksheet — sign-off pending

Ground truth currently lives in `seed()` in `cra-service/test_phase4_api.py`.
It is Team 2 synthetic test data, separate from the unchanged Team 6 Phase 3
fixtures. Freeze the reviewed commit and its file SHA-256 with the report.

At reference UTC date 2026-11-01:

| Release version | Inventory (including nested child) | Support group |
|---|---|---|
| 0 | alpha@1, beta@2 | supported through today |
| 1 | alpha@1, gamma@4 | unsupported (ended 2026-10-31) |
| 2 | alpha@9, delta@5 | supported (ends 2028-01-01) |

All packages have prefix `pkg:generic/`. Expected sets:

| CVE | Affected versions in manifest | Expected release: matched components |
|---|---|---|
| CVE-2026-100 | alpha@1 | 0: alpha@1; 1: alpha@1 |
| CVE-2026-101 | beta@2 | 0: beta@2 |
| CVE-2026-102 | alpha@9 | 2: alpha@9 |
| CVE-2026-103 | gamma@4, delta@5 | 1: gamma@4; 2: delta@5 |
| CVE-2026-104 | alpha@1, beta@2, gamma@4 | 0: alpha@1, beta@2; 1: alpha@1, gamma@4 |

Additional known-unaffected CVE-2026-999 lists absent@1 and returns empty groups.
Compare release IDs and `(name, version, purl)` sets; also reject duplicate
release/component results in these unique fixtures. No response ordering is
required. Exact equality enforces 100% precision and recall for this manifest;
it is not an estimate for all OSV data. Separate regressions cover qualifiers,
subpaths, mismatched versions and missing component PURLs.

| Required review evidence | State |
|---|---|
| Team 2 reviewer name/date/commit/hash and independent expected-set check | Pending |
| Team 6 reviewer name/date/commit/hash and independent expected-set check | Pending |
| Agreed review deadline | Before Phase 4 submission; exact date pending |
| Shared manifest approval and both-direction execution results | Pending |

Attach both reviewers' actual responses and test evidence before marking this
complete. The supplied conversation contains a proposal to designate reviewers,
not reviewer names, completed review or Team 6 confirmation.
