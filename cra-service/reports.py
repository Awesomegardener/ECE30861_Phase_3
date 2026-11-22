"""Stage report data and generation (REQ-07, AC-08), following pod Phase 5 Q1-Q4.

PUT replaces a stage's whole data and returns the generated report; GET returns
only the supplied fields plus missing_fields and stores nothing. Checks run in
the agreed order: X-User-Id, unknown incident (404), invalid stage, body.
"""

import datetime as dt
import json
from typing import Any

import audit
from fastapi import APIRouter, Header, HTTPException, Request
from psycopg2.extras import Json
from pydantic import AwareDatetime, BaseModel
from starlette.concurrency import run_in_threadpool

UTC = dt.timezone.utc
STAGES = ("early_warning", "vulnerability_notification", "final_report")

# CRA Art. 14(2)(a)-(c), as agreed in pod Phase 5 Q1.
REQUIRED = {
    "early_warning": ("member_states",),
    "vulnerability_notification": (
        "product_information",
        "exploit_nature",
        "vulnerability_nature",
        "corrective_measures_taken",
        "user_mitigations",
    ),
    "final_report": (
        "vulnerability_description",
        "severity",
        "impact",
        "corrective_measure_details",
    ),
}
OPTIONAL = {
    "early_warning": (),
    "vulnerability_notification": ("sensitivity",),
    "final_report": ("malicious_actor_information",),
}
ALL_FIELDS = {field for stage in STAGES for field in (*REQUIRED[stage], *OPTIONAL[stage])}
ARRAY_FIELDS = {"member_states"}

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS report_data (
        incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
        stage TEXT NOT NULL CHECK
            (stage IN ('early_warning','vulnerability_notification','final_report')),
        data JSONB NOT NULL,
        updated_by TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (incident_id, stage)
    )""",
)


def fail(status, code, message):
    raise HTTPException(status, detail={"error": {"code": code, "message": message}})


def check_stage(stage):
    if stage not in STAGES:
        fail(400, "INVALID_REQUEST", f"stage must be one of: {', '.join(STAGES)}")


def _has_nul(value):
    return "\x00" in value


def validate_data(stage, payload):
    """Return the payload unchanged if valid for the stage, otherwise raise 400."""
    if not isinstance(payload, dict):
        fail(400, "INVALID_REQUEST", "Report data must be a JSON object")
    allowed = (*REQUIRED[stage], *OPTIONAL[stage])
    for field, value in payload.items():
        if field not in allowed:
            if field in ALL_FIELDS:
                fail(
                    400, "INVALID_REQUEST", f"{field} belongs to another report stage, not {stage}"
                )
            fail(400, "INVALID_REQUEST", f"{field} is not a known report field")
        if value is None:
            continue  # Accepted and reported as missing (Team 2 proposal on pod Q2).
        if field in ARRAY_FIELDS:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                fail(400, "INVALID_REQUEST", f"{field} must be an array of strings")
            if any(_has_nul(item) for item in value):
                fail(400, "INVALID_REQUEST", f"{field} must not contain NUL characters")
        else:
            if not isinstance(value, str):
                fail(400, "INVALID_REQUEST", f"{field} must be a string")
            if _has_nul(value):
                fail(400, "INVALID_REQUEST", f"{field} must not contain NUL characters")
    return payload


def missing_fields(stage, data):
    """Required fields that are absent, null, blank strings or an empty array (pod Q2)."""
    missing = []
    for field in REQUIRED[stage]:
        value = data.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)
        elif isinstance(value, list) and not value:
            missing.append(field)
    return missing


def _stamp(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def generated_report(incident_id, stage, data, now):
    return {
        "incident_id": incident_id,
        "stage": stage,
        "generated_at": _stamp(now),
        "data": data,
        "missing_fields": missing_fields(stage, data),
    }


class GeneratedReport(BaseModel):
    incident_id: str
    stage: str
    generated_at: AwareDatetime
    data: dict[str, Any]
    missing_fields: list[str]


def install(app, database, current_time, error_model):
    router = APIRouter(prefix="/api/v1")
    errors: dict[int | str, dict[str, Any]] = {
        400: {"model": error_model},
        404: {"model": error_model},
    }

    def load(cur, incident_id, *, lock):
        cur.execute(
            "SELECT incident_id FROM incidents WHERE incident_id=%s"
            + (" FOR UPDATE" if lock else " FOR SHARE"),
            (incident_id,),
        )
        if cur.fetchone() is None:
            fail(404, "NOT_FOUND", "Incident not found")

    def store(incident_id, stage, raw, user_id):
        with database() as conn, conn.cursor() as cur:
            load(cur, incident_id, lock=True)
            check_stage(stage)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                fail(400, "INVALID_JSON", "Request body is not valid JSON")
            data = validate_data(stage, payload)
            now = current_time(cur)
            cur.execute(
                "INSERT INTO report_data (incident_id, stage, data, updated_by, updated_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (incident_id, stage) DO UPDATE SET "
                "data=EXCLUDED.data, updated_by=EXCLUDED.updated_by, updated_at=EXCLUDED.updated_at",
                (incident_id, stage, Json(data), user_id, now),
            )
            audit.record(
                cur,
                at=now,
                user_id=user_id,
                action="REPORT_DATA_STORED",
                entity_type="incident",
                entity_id=incident_id,
                details={"stage": stage, "fields": sorted(data)},
            )
            return generated_report(incident_id, stage, data, now)

    @router.put(
        "/incidents/{incidentId}/report-data/{stage}",
        response_model=GeneratedReport,
        responses=errors,
    )
    async def put_report_data(
        incidentId: str,
        stage: str,
        request: Request,
        x_user_id: str = Header(..., alias="X-User-Id", min_length=1),
    ):
        # The raw body is read here and validated after the incident and stage
        # checks so the agreed 404-before-400 order holds for every body.
        raw = await request.body()
        return await run_in_threadpool(store, incidentId, stage, raw, x_user_id)

    @router.get(
        "/incidents/{incidentId}/reports/{stage}",
        response_model=GeneratedReport,
        responses=errors,
    )
    def get_report(incidentId: str, stage: str):
        with database() as conn, conn.cursor() as cur:
            load(cur, incidentId, lock=False)
            check_stage(stage)
            cur.execute(
                "SELECT data FROM report_data WHERE incident_id=%s AND stage=%s",
                (incidentId, stage),
            )
            row = cur.fetchone()
            now = current_time(cur)
        return generated_report(incidentId, stage, row["data"] if row else {}, now)

    app.include_router(router)
