# OSV snapshot operations and limits

The production source defaults to `VULNERABILITY_SOURCE=osv`. It reads real OSV
documents in PostgreSQL, not the deterministic test fixture table. No active
snapshot, stale data, unsupported comparisons, invalid freshness configuration,
or database connection failure returns 503 `VULNERABILITY_SOURCE_UNREACHABLE`.
An unknown CVE in a fresh active snapshot returns 404 `CVE_UNKNOWN`; a known CVE
with no affected inventory returns 200 with empty groups. Absence means unknown
**within the recorded scope**, not proof that a package is safe globally.

## Fetch, review, import

Use the repository virtual environment with its installed requirements. These
commands write an ignored local file and contact only official public OSV data:

```powershell
python scripts/osv_snapshot.py fetch --id GHSA-j8r2-6x86-q33q --output artifacts/osv/selected-advisory.json
# Or, for a separately reviewed larger scope:
python scripts/osv_snapshot.py fetch --ecosystem PyPI --output artifacts/osv/pypi.json
```

The fetcher rejects redirects, credentials, proxies and non-allowlisted URLs,
verifies TLS normally, records the upstream artifact SHA-256 and UTC fetch time,
and saves without overwriting. ZIP entries are read without filesystem extraction.
Limits: 64 MiB upstream; 2 MiB per ZIP record; 256 MiB expanded bundle; 50,000
records. A feed exceeding these limits is refused, not silently truncated.
Assembling a larger/multi-ecosystem snapshot is **not implemented**. Fetching a
single advisory is useful for verification, not an adequate general feed.

Review the scope and the printed bundle hash. In an explicitly approved runtime
with `DATABASE_URL` already supplied securely, initialize the additive schema by
starting the application, then run:

```powershell
python scripts/osv_snapshot.py import --snapshot artifacts/osv/pypi.json --sha256 REVIEWED_64_HEX_HASH --database-name APPROVED_OSV_DATABASE --allow-import
python scripts/osv_snapshot.py inspect
```

Do not put a real DSN on the command line or in source. Import refuses
`cra_phase3`, system databases and actual/approved database-name mismatches. It
validates every record and checksum before writing. One transaction creates a
generation, raw records and CVE/alias index, then switches the active pointer.
SQL failure leaves the previous generation active. History is retained; no
automatic retention/delete policy exists. Inspect reports provenance, not secrets.
Offline provenance is operator-attested; a hash is integrity evidence, not a
signature proving the contents originated at OSV. Use the HTTPS fetcher and keep
its original output when origin evidence matters.

The official OSV validation schema/license is pinned in `cra-service/vendor/osv`.
`SOURCE.json` records the upstream commit and schema SHA-256, checked before
validation. No schema download occurs at runtime.

## Matching and freshness

OSV IDs and CVE aliases index the active generation. Package identity uses a
versioned PURL, ignoring qualifiers/subpaths. An upstream package PURL or supported
ecosystem/name mapping identifies the package; package names alone never match a
stored component without a PURL. Explicit OSV versions match exactly. OSV ranges
use SEMVER ordering or PyPI/PEP 440 ordering; introduced is inclusive, fixed and
limit are exclusive, last_affected inclusive. Withdrawn records do not match.
This range evaluation is separate from fixture `affected_purls`, which enumerate
exact versions only.

Unsupported native ECOSYSTEM comparisons and GIT ranges produce explicit 503
where a reliable answer is unavailable. No external Git graph, NVD fallback,
Dependency-Track scan, CPE matching or universal ecosystem completeness is claimed.
The official schema permits records without affected entries; these have no
declared affected packages and cannot establish broad coverage.

`OSV_SNAPSHOT_MAX_AGE_SECONDS` defaults to 604800 (7 days), allowed 1..7776000.
Freshness uses wall-clock UTC, never `/test/clock`. Fetch times over five minutes
ahead fail; stale snapshots fail closed before unknown-CVE responses. Choose and
document an operational refresh interval shorter than the selected limit and
monitor inspect metadata. Automatic scheduling, upstream-update monitoring and
large-feed performance validation remain deployment tasks.

## Grading source and evidence

The 353 portable cases require `VULNERABILITY_SOURCE=fixture`,
`VULNERABILITY_TEST_MODE=true`, and `VULNERABILITY_TEST_DATABASE=cra_grading`
(or `cra_test` only for isolated local tests). Actual DB identity must match.
PUT replaces the entire fixture dataset; reset sets available with zero records.
Neither operation changes an OSV snapshot. OSV mode refuses fixture injection;
non-grading databases refuse reset. Do not run the reset-based portable suite
against a production OSV database.

Local verification includes real HTTPS-fetched `GHSA-j8r2-6x86-q33q`, alias
`CVE-2023-32681`: requests 2.30.0 matches, fixed 2.31.0 does not. Synthetic raw OSV
integration also checks atomic activation rollback, stale/unsupported data,
storage failure, restart persistence and reset refusal. This is local evidence,
not deployed results or complete-feed acceptance.

## Production-readiness review before the first OSV deployment

The durable source is the configured PostgreSQL database (Cloud SQL when deployed),
not the Cloud Run filesystem. `osv_snapshots` stores generation provenance;
`osv_records` stores raw JSONB; `osv_cves` indexes identifiers/aliases; `osv_active`
selects the committed generation. Queries read these tables. The fetch bundle is
an import input only: losing that temporary file after a successful commit does
not lose the active source. API restart persistence was verified in isolated
Docker PostgreSQL, not on Cloud SQL. Optional archival in object storage is an
operational choice, not an implemented storage integration.

Population requires an operator-controlled initial fetch, scope/hash review and
explicit CLI import after additive schema initialization. An approved Cloud Run
Job could fetch and import in the same execution using temporary storage, or an
operator could use an authorized Cloud SQL Auth Proxy. Neither path is deployed
or automated here. Inject the approved database secret/SQL attachment into that
runtime; do not publish an import endpoint or use the retained `cra_phase3` DB.

Refresh repeats the complete validated generation import rather than appending
to the active dataset. The previous active generation survives a failed import;
successful prior generations remain stored. Schedule refresh substantially before
the seven-day default expiry (a proposed daily refresh needs separate approval),
and alert on importer failure and metadata age. No scheduler, alert, retention
cleanup or production coverage policy is configured yet. `/health/ready` checks
database availability only: HTTP200 there does **not** certify a populated/fresh
OSV source. Monitor `inspect` and representative read-only CVE queries separately.

Before production sign-off, review the selected scope, supported ecosystems,
full-feed download limits and peak JSON validation/import memory. A bounded256MiB
input can consume much more memory after parsing; the recommended1GiB API setting
is not proof that a maximum-sized import fits. Measure import/query performance
and storage growth with the actual feed. Unsupported comparisons, stale/no
snapshot and source-storage errors return503; no automatic fixture fallback is
permitted. All source durability/freshness conclusions here are code/local-test
evidence; no cloud database or deployed resource was accessed for this review.

References: [OSV schema semantics](https://ossf.github.io/osv-schema/),
[official data exports](https://google.github.io/osv.dev/data/),
[verified advisory](https://osv.dev/vulnerability/GHSA-j8r2-6x86-q33q).
