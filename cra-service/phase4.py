"""Phase 4 operations backed by local OSV snapshots or an isolated fixture source."""

import datetime as dt
import os
import re
import uuid
from functools import wraps
from typing import Annotated, Any, Literal

import osv_source
import psycopg2
from fastapi import APIRouter, Header, HTTPException, Path
from psycopg2.extras import Json
from purl_matching import exact_purl
from pydantic import AwareDatetime, BaseModel, BeforeValidator, StrictStr, field_validator
from timestamps import validate_timestamp

UTC = dt.timezone.utc
Timestamp = Annotated[AwareDatetime, BeforeValidator(validate_timestamp)]
Stage = Literal["early_warning", "vulnerability_notification", "final_report"]
STAGES = ("early_warning", "vulnerability_notification", "final_report")
SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY, cve_id TEXT,
        awareness_at TIMESTAMPTZ NOT NULL, created_by TEXT NOT NULL,
        classification TEXT NOT NULL CHECK (classification IN ('mandatory','voluntary')),
        rationale TEXT NOT NULL CHECK (length(rationale) > 0),
        fix_available_at TIMESTAMPTZ, updated_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS incident_submissions (
        submission_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
        stage TEXT NOT NULL CHECK
            (stage IN ('early_warning','vulnerability_notification','final_report')),
        submitted_at TIMESTAMPTZ NOT NULL, recorded_by TEXT NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS incident_submissions_lookup
       ON incident_submissions (incident_id, stage, submitted_at)""",
    """CREATE TABLE IF NOT EXISTS test_vulnerability_source (
        id INTEGER PRIMARY KEY CHECK (id=1),
        mode TEXT NOT NULL CHECK (mode IN ('available','unreachable')),
        records JSONB NOT NULL
    )""",
    # Equality-only hash index avoids B-tree entry-size limits on valid long PURLs.
    "CREATE INDEX IF NOT EXISTS components_purl_lookup ON components USING hash (purl)",
)


class IncidentCreate(BaseModel):
    awareness_at: Timestamp
    classification: Literal["mandatory", "voluntary"]
    rationale: StrictStr
    cve_id: StrictStr | None = None

    @field_validator("cve_id")
    @classmethod
    def valid_cve(cls, value):
        if value is not None and not re.fullmatch(osv_source.CVE_PATTERN, value):
            raise ValueError("cve_id must have the form CVE-YYYY-NNNN")
        return value

    @field_validator("rationale")
    @classmethod
    def nonempty_rationale(cls, value):
        if not value.strip():
            raise ValueError("rationale must contain text")
        return value  # Preserve the original text, including surrounding whitespace.


class IncidentUpdate(BaseModel):
    fix_available_at: Timestamp


class SubmissionCreate(BaseModel):
    stage: Stage
    submitted_at: Timestamp


class VulnerabilityFixture(BaseModel):
    cve_id: StrictStr
    affected_purls: list[StrictStr]


class SourceUpdate(BaseModel):
    mode: Literal["available", "unreachable"]
    records: list[VulnerabilityFixture] | None = None

    @field_validator("records", mode="before")
    @classmethod
    def records_not_null(cls, value):
        if value is None:
            raise ValueError("records must be an array when supplied")
        return value


class DeadlineRecord(BaseModel):
    deadline_at: AwareDatetime | None
    submitted_at: AwareDatetime | None
    status: Literal["pending", "met", "overdue", "not_applicable"]


class DeadlinesRecord(BaseModel):
    early_warning: DeadlineRecord
    vulnerability_notification: DeadlineRecord
    final_report: DeadlineRecord


class IncidentRecord(BaseModel):
    incident_id: str
    cve_id: str | None
    awareness_at: AwareDatetime
    created_by: str
    classification: Literal["mandatory", "voluntary"]
    rationale: str
    fix_available_at: AwareDatetime | None
    deadlines: DeadlinesRecord


class MatchedComponent(BaseModel):
    name: str
    version: str
    purl: str | None


class AffectedRelease(BaseModel):
    release_id: str
    product: str
    version: str
    support_end_date: dt.date
    matched_components: list[MatchedComponent]


class AffectedResult(BaseModel):
    cve_id: str
    supported: list[AffectedRelease]
    unsupported: list[AffectedRelease]


def fail(status, code, message):
    raise HTTPException(status, detail={"error": {"code": code, "message": message}})


def source_failures(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except psycopg2.Error:
            # Local OSV storage failure must not look like a negative CVE lookup.
            fail(503, "VULNERABILITY_SOURCE_UNREACHABLE", "Vulnerability storage is unavailable")

    return wrapped


def utc(value):
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        fail(400, "INVALID_REQUEST", "Timestamp is outside the supported UTC range")


def stamp(value):
    return utc(value).isoformat().replace("+00:00", "Z") if value is not None else None


def add_time(value, *, hours=0, days=0):
    try:
        return utc(value) + dt.timedelta(hours=hours, days=days)
    except (OverflowError, ValueError):
        fail(400, "INVALID_REQUEST", "Timestamp is outside the supported deadline range")


def deadline(due, submitted, now, *, applicable=True):
    if not applicable:
        status = "not_applicable"
    elif due is None:
        # Phase 2 section 5.2's incident example has no final deadline until a fix.
        status = "not_applicable"
    elif submitted is not None:
        status = "met" if submitted <= due else "overdue"
    else:
        status = "overdue" if now > due else "pending"
    return dict(deadline_at=stamp(due), submitted_at=stamp(submitted), status=status)


def incident_response(cur, row, now):
    cur.execute(
        "SELECT stage, min(submitted_at) AS submitted_at FROM incident_submissions "
        "WHERE incident_id=%s GROUP BY stage",
        (row["incident_id"],),
    )
    submissions = {item["stage"]: item["submitted_at"] for item in cur.fetchall()}
    mandatory = row["classification"] == "mandatory"
    due = {
        "early_warning": add_time(row["awareness_at"], hours=24) if mandatory else None,
        "vulnerability_notification": add_time(row["awareness_at"], hours=72)
        if mandatory
        else None,
        "final_report": add_time(row["fix_available_at"], days=14)
        if mandatory and row["fix_available_at"]
        else None,
    }
    return dict(
        incident_id=row["incident_id"],
        cve_id=row["cve_id"],
        awareness_at=stamp(row["awareness_at"]),
        created_by=row["created_by"],
        classification=row["classification"],
        rationale=row["rationale"],
        fix_available_at=stamp(row["fix_available_at"]),
        deadlines={
            stage: deadline(due[stage], submissions.get(stage), now, applicable=mandatory)
            for stage in STAGES
        },
    )


def require_test_source(cur):
    # Names are deliberately bounded; a typo or retained cra_phase3 DB cannot opt in.
    expected = os.getenv("VULNERABILITY_TEST_DATABASE", "cra_grading")
    if (
        os.getenv("VULNERABILITY_SOURCE", "osv") != "fixture"
        or os.getenv("VULNERABILITY_TEST_MODE", "false").lower() != "true"
        or expected
        not in {
            "cra_grading",
            "cra_test",
        }
    ):
        fail(
            503,
            "VULNERABILITY_SOURCE_UNREACHABLE",
            "Fixture source is disabled; configure a fresh OSV snapshot for production",
        )
    cur.execute("SELECT current_database() AS name")
    if cur.fetchone()["name"] != expected:
        fail(
            503,
            "VULNERABILITY_SOURCE_UNREACHABLE",
            "Test source requires the explicitly configured disposable database",
        )


def require_reset_database(cur):
    cur.execute("SELECT current_database() AS name")
    if cur.fetchone()["name"] not in {"cra_grading", "cra_test"}:
        fail(503, "RESET_DISABLED", "Reset requires a disposable grading database")


def reset_phase4(cur):
    cur.execute("TRUNCATE incidents CASCADE")
    cur.execute(
        "INSERT INTO test_vulnerability_source (id,mode,records) VALUES (1,'available','[]'::jsonb) ON CONFLICT(id) DO UPDATE SET mode='available',records='[]'::jsonb"
    )


def install(app, database, current_time, error_model):
    router = APIRouter(prefix="/api/v1")
    errors: dict[int | str, dict[str, Any]] = {
        400: {"model": error_model},
        404: {"model": error_model},
    }

    def load(cur, incident_id, *, update=False):
        cur.execute(
            "SELECT * FROM incidents WHERE incident_id=%s"
            + (" FOR UPDATE" if update else " FOR SHARE"),
            (incident_id,),
        )
        row = cur.fetchone()
        if row is None:
            fail(404, "NOT_FOUND", "Incident not found")
        return row

    @router.put(
        "/test/vulnerability-source",
        responses={400: {"model": error_model}, 503: {"model": error_model}},
    )
    def configure_source(source: SourceUpdate):
        with (
            database(statement_timeout_ms=3000, lock_timeout_ms=2000) as conn,
            conn.cursor() as cur,
        ):
            require_test_source(cur)
            # Every PUT replaces the complete fixture dataset; omitted means empty.
            records = (
                [r.model_dump() for r in source.records] if source.records is not None else None
            )
            cur.execute(
                "INSERT INTO test_vulnerability_source (id,mode,records) VALUES (1,%s,%s) "
                "ON CONFLICT (id) DO UPDATE SET mode=EXCLUDED.mode, records=EXCLUDED.records",
                (source.mode, Json(records or [])),
            )
        return {"mode": source.mode}

    @router.get(
        "/vulnerabilities/{cveId}/affected-releases",
        response_model=AffectedResult,
        responses={
            400: {"model": error_model},
            404: {"model": error_model},
            503: {"model": error_model},
        },
    )
    @source_failures
    def affected_releases(cveId: str = Path(..., pattern=r"^CVE-[0-9]{4}-[0-9]+$")):
        with (
            database(statement_timeout_ms=3000, lock_timeout_ms=2000) as conn,
            conn.cursor() as cur,
        ):
            # Use one snapshot for source, inventory and clock under concurrent writes.
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            kind = os.getenv("VULNERABILITY_SOURCE", "osv")
            try:
                if kind == "fixture":
                    require_test_source(cur)
                    cur.execute("SELECT mode, records FROM test_vulnerability_source WHERE id=1")
                    source = cur.fetchone() or {"mode": "available", "records": []}
                    if source["mode"] == "unreachable":
                        raise osv_source.SourceUnavailable(
                            "Vulnerability fixture source is unavailable"
                        )
                    records = [r for r in source["records"] if r["cve_id"] == cveId]
                elif kind == "osv":
                    records = osv_source.read_records(cur, cveId)
                else:
                    raise osv_source.SourceUnavailable("Unknown vulnerability source configuration")
            except osv_source.SourceUnavailable as exc:
                fail(503, "VULNERABILITY_SOURCE_UNREACHABLE", str(exc))
            if not records:
                fail(404, "CVE_UNKNOWN", "CVE identifier is not known to the configured source")
            purls = {exact_purl(p) for r in records for p in r.get("affected_purls", [])} - {None}
            cur.execute(
                "SELECT r.*, c.name, c.version AS component_version, c.purl "
                "FROM releases r JOIN components c USING(release_id) "
                "WHERE c.purl IS NOT NULL ORDER BY r.release_id, c.id",
            )
            rows = cur.fetchall()
            today = utc(current_time(cur)).date()
            result: dict = dict(cve_id=cveId, supported=[], unsupported=[])
            releases: dict = {}
            for row in rows:
                component = dict(
                    name=row["name"], version=row["component_version"], purl=row["purl"]
                )
                try:
                    if kind == "fixture":
                        matched = exact_purl(row["purl"]) in purls
                    else:
                        matched = osv_source.records_match(records, component)
                except osv_source.SourceUnavailable as exc:
                    fail(503, "VULNERABILITY_SOURCE_UNREACHABLE", str(exc))
                if not matched:
                    continue
                release_id = row["release_id"]
                if release_id not in releases:
                    item = {k: row[k] for k in ("release_id", "product", "version")}
                    item.update(
                        support_end_date=str(row["support_end_date"]), matched_components=[]
                    )
                    releases[release_id] = item
                    group = "supported" if today <= row["support_end_date"] else "unsupported"
                    result[group].append(item)
                releases[release_id]["matched_components"].append(component)
        return result

    @router.post(
        "/incidents",
        status_code=201,
        response_model=IncidentRecord,
        responses={400: {"model": error_model}},
    )
    def create_incident(
        incident: IncidentCreate, x_user_id: str = Header(..., alias="X-User-Id", min_length=1)
    ):
        if incident.classification == "mandatory":
            add_time(incident.awareness_at, hours=72)
        incident_id = "inc-" + uuid.uuid4().hex
        with database() as conn, conn.cursor() as cur:
            # Acquire the insert's table lock before reading the clock, matching
            # reset's incidents -> clock lock order and keeping the response atomic.
            cur.execute("LOCK TABLE incidents IN ROW EXCLUSIVE MODE")
            now = current_time(cur)
            cur.execute(
                "INSERT INTO incidents (incident_id,cve_id,awareness_at,created_by,classification,"
                "rationale,updated_by,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (
                    incident_id,
                    incident.cve_id,
                    utc(incident.awareness_at),
                    x_user_id,
                    incident.classification,
                    incident.rationale,
                    x_user_id,
                    now,
                    now,
                ),
            )
            response = incident_response(cur, cur.fetchone(), now)
        return response

    @router.get(
        "/incidents/{incidentId}",
        response_model=IncidentRecord,
        responses={404: {"model": error_model}},
    )
    def get_incident(incidentId: str):
        with database() as conn, conn.cursor() as cur:
            response = incident_response(cur, load(cur, incidentId), current_time(cur))
        return response

    @router.patch("/incidents/{incidentId}", response_model=IncidentRecord, responses=errors)
    def update_incident(
        incidentId: str,
        update: IncidentUpdate,
        x_user_id: str = Header(..., alias="X-User-Id", min_length=1),
    ):
        with database() as conn, conn.cursor() as cur:
            row = load(cur, incidentId, update=True)
            if utc(update.fix_available_at) < row["awareness_at"]:
                fail(400, "INVALID_REQUEST", "fix_available_at cannot be earlier than awareness_at")
            if row["classification"] == "mandatory":
                add_time(update.fix_available_at, days=14)
            now = current_time(cur)
            cur.execute(
                "UPDATE incidents SET fix_available_at=%s,updated_by=%s,updated_at=%s "
                "WHERE incident_id=%s RETURNING *",
                (utc(update.fix_available_at), x_user_id, now, incidentId),
            )
            response = incident_response(cur, cur.fetchone(), now)
        return response

    @router.post(
        "/incidents/{incidentId}/submissions",
        status_code=201,
        response_model=IncidentRecord,
        responses={**errors, 409: {"model": error_model}},
    )
    def record_submission(
        incidentId: str,
        submission: SubmissionCreate,
        x_user_id: str = Header(..., alias="X-User-Id", min_length=1),
    ):
        with database() as conn, conn.cursor() as cur:
            row = load(cur, incidentId, update=True)
            submitted_at = utc(submission.submitted_at)
            if submitted_at < row["awareness_at"]:
                fail(400, "INVALID_REQUEST", "submitted_at cannot be earlier than awareness_at")
            if row["classification"] == "voluntary" or (
                submission.stage == "final_report" and row["fix_available_at"] is None
            ):
                fail(400, "INVALID_REQUEST", "Cannot submit a not_applicable stage")
            cur.execute(
                "SELECT 1 FROM incident_submissions WHERE incident_id=%s AND stage=%s LIMIT 1",
                (incidentId, submission.stage),
            )
            if cur.fetchone():
                fail(409, "CONFLICT", "A submission for this stage already exists")
            now = current_time(cur)
            cur.execute(
                "INSERT INTO incident_submissions (submission_id,incident_id,stage,submitted_at,recorded_by,recorded_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    uuid.uuid4().hex,
                    incidentId,
                    submission.stage,
                    submitted_at,
                    x_user_id,
                    now,
                ),
            )
            response = incident_response(cur, row, now)
        return response

    app.include_router(router)
