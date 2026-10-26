"""Durable JSON reports and one cross-service PostgreSQL execution lock.

Use a separate metadata database on the existing Cloud SQL instance. CRA reset
never touches this schema. All adapter deployments must share this database.
"""

from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json

from .config import HarnessError

LOCK = 308612026
SCHEMA_LOCK = 308612027


class Store:
    def __init__(self, dsn):
        self.dsn = dsn

    @contextmanager
    def connection(self):
        conn = psycopg2.connect(
            self.dsn,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=3000 -c timezone=UTC",
        )
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
                cur.execute("CREATE SCHEMA IF NOT EXISTS autograder")
                cur.execute("""CREATE TABLE IF NOT EXISTS autograder.sessions (
                    role TEXT NOT NULL, session_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    report JSONB NOT NULL, PRIMARY KEY (role, session_id))""")
            conn.autocommit = True
            yield conn
        finally:
            conn.close()

    @contextmanager
    def guard(self):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,))
            if not cur.fetchone()[0]:
                raise HarnessError(409, "RUN_IN_PROGRESS", "Another setup or run is in progress")
            try:
                self.recover(conn)
                yield conn
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))

    def recover(self, conn):
        # Only the lock holder may declare an abandoned run interrupted.
        with conn.cursor() as cur:
            cur.execute("""UPDATE autograder.sessions SET report = report || jsonb_build_object(
                'status', 'completed', 'running', false, 'result', 'error',
                'error', 'Execution interrupted before a complete report was saved',
                'finished_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))
                WHERE report->>'running' = 'true'""")

    def get(self, conn, role, identifier=None):
        with conn.cursor() as cur:
            if identifier is None:
                cur.execute(
                    "SELECT report FROM autograder.sessions WHERE role=%s ORDER BY created_at DESC, session_id DESC LIMIT 1",
                    (role,),
                )
            else:
                cur.execute(
                    "SELECT report FROM autograder.sessions WHERE role=%s AND session_id=%s",
                    (role, identifier),
                )
            row = cur.fetchone()
        return row[0] if row else None

    def create(self, conn, report):
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO autograder.sessions (role, session_id, report) VALUES (%s,%s,%s)",
                    (report["role"], report["session_id"], Json(report)),
                )
            except psycopg2.errors.UniqueViolation:
                raise HarnessError(
                    409, "SESSION_EXISTS", "Use a new session_id; existing reports are retained"
                ) from None

    def save(self, conn, report):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE autograder.sessions SET report=%s WHERE role=%s AND session_id=%s",
                (Json(report), report["role"], report["session_id"]),
            )

    def read(self, role, identifier=None):
        # Recovery is read-triggered after a hard restart, including no next run.
        with self.connection() as conn, conn.cursor() as cur:
            report = self.get(conn, role, identifier)
            # Ordinary polling must not compete with run/setup for the mutex.
            if not report or not report.get("running"):
                return report
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,))
            if cur.fetchone()[0]:
                try:
                    self.recover(conn)
                finally:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
            return self.get(conn, role, identifier)
