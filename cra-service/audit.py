"""Append-only audit log (REQ-08, AC-09).

Every successful state change records exactly one event in the same database
transaction as the change, so a rolled-back request leaves no audit entry.
Immutability is enforced by PostgreSQL itself: row triggers reject UPDATE and
DELETE for every caller, and a statement trigger allows TRUNCATE only in the
disposable test databases used by /api/v1/test/reset.
"""

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from psycopg2.extras import Json
from pydantic import AwareDatetime, BaseModel

UTC = dt.timezone.utc
DISPOSABLE_DATABASES = ("cra_grading", "cra_test")

ACTIONS = (
    "RELEASE_REGISTERED",
    "SBOM_STORED",
    "SBOM_REPLACED",
    "INCIDENT_CREATED",
    "FIX_AVAILABLE_RECORDED",
    "SUBMISSION_RECORDED",
    "REPORT_DATA_STORED",
)

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS audit_events (
        seq BIGSERIAL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_time TIMESTAMPTZ NOT NULL,
        user_id TEXT NOT NULL CHECK (length(user_id) > 0),
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        details JSONB NOT NULL DEFAULT '{}'::jsonb
    )""",
    """CREATE INDEX IF NOT EXISTS audit_events_order ON audit_events (event_time, seq)""",
    """CREATE INDEX IF NOT EXISTS audit_events_entity ON audit_events (entity_type, entity_id)""",
    """CREATE OR REPLACE FUNCTION audit_events_reject_change() RETURNS trigger
       LANGUAGE plpgsql AS $$
       BEGIN
           RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
               USING ERRCODE = 'insufficient_privilege';
       END $$""",
    """CREATE OR REPLACE FUNCTION audit_events_guard_truncate() RETURNS trigger
       LANGUAGE plpgsql AS $$
       BEGIN
           IF current_database() NOT IN ('cra_grading', 'cra_test') THEN
               RAISE EXCEPTION 'audit_events may only be truncated by a test reset'
                   USING ERRCODE = 'insufficient_privilege';
           END IF;
           RETURN NULL;
       END $$""",
    # Create the triggers once; repeated startups must not take ALTER-level locks.
    """DO $$
       BEGIN
           IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'audit_events_no_update_delete'
                          AND tgrelid = 'audit_events'::regclass) THEN
               CREATE TRIGGER audit_events_no_update_delete
                   BEFORE UPDATE OR DELETE ON audit_events
                   FOR EACH ROW EXECUTE FUNCTION audit_events_reject_change();
           END IF;
           IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'audit_events_truncate_guard'
                          AND tgrelid = 'audit_events'::regclass) THEN
               CREATE TRIGGER audit_events_truncate_guard
                   BEFORE TRUNCATE ON audit_events
                   FOR EACH STATEMENT EXECUTE FUNCTION audit_events_guard_truncate();
           END IF;
       END $$""",
)


def record(cur, *, at, user_id, action, entity_type, entity_id, details=None):
    """Append one event inside the caller's transaction."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown audit action {action}")
    cur.execute(
        "INSERT INTO audit_events (event_id, event_time, user_id, action, entity_type, entity_id, details) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            "evt-" + uuid.uuid4().hex,
            at.astimezone(UTC),
            user_id,
            action,
            entity_type,
            entity_id,
            Json(details or {}),
        ),
    )


def has_event(cur, *, entity_type, entity_id, actions):
    cur.execute(
        "SELECT 1 FROM audit_events WHERE entity_type = %s AND entity_id = %s AND action = ANY(%s) LIMIT 1",
        (entity_type, entity_id, list(actions)),
    )
    return cur.fetchone() is not None


def reset(cur):
    """Clear audit events; the database trigger refuses outside disposable databases."""
    cur.execute("TRUNCATE audit_events")


def _stamp(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class AuditEventRecord(BaseModel):
    event_id: str
    timestamp: AwareDatetime
    user_id: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]


class AuditLog(BaseModel):
    events: list[AuditEventRecord]


def install(app, database, error_model):
    router = APIRouter(prefix="/api/v1")

    @router.get("/audit-logs", response_model=AuditLog)
    def list_audit_events():
        with database() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT event_id, event_time, user_id, action, entity_type, entity_id, details "
                "FROM audit_events ORDER BY event_time, seq"
            )
            rows = cur.fetchall()
        return {
            "events": [
                {
                    "event_id": row["event_id"],
                    "timestamp": _stamp(row["event_time"]),
                    "user_id": row["user_id"],
                    "action": row["action"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "details": row["details"],
                }
                for row in rows
            ]
        }

    def immutable():
        # The answer is the same whether or not the event exists, and nothing is read.
        return JSONResponse(
            status_code=405,
            content={"error": {"code": "METHOD_NOT_ALLOWED", "message": "Audit log is immutable"}},
            headers={"Allow": ""},
        )

    responses: dict[int | str, dict[str, Any]] = {405: {"model": error_model}}

    @router.patch("/audit-logs/{eventId}", status_code=405, responses=responses)
    def modify_audit_event(eventId: str):
        return immutable()

    @router.delete("/audit-logs/{eventId}", status_code=405, responses=responses)
    def delete_audit_event(eventId: str):
        return immutable()

    app.include_router(router)
