"""Run in the fresh test Compose API; never reset/drop an existing database."""

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import main as application
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def connect(dsn):
    return psycopg2.connect(dsn, connect_timeout=5, cursor_factory=RealDictCursor)


def snapshot(dsn):
    conn = connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            result = {}
            for table in ("releases", "components", "test_clock"):
                cur.execute(sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(table)))
                result[table] = [dict(row) for row in cur.fetchall()]
            return result
    finally:
        conn.close()


def main():
    base = os.environ["DATABASE_URL"]
    admin = connect(base)
    created = []
    checks = []
    try:
        parameters = admin.get_dsn_parameters()
        assert parameters["dbname"] == "cra_test" and parameters["host"] == "db", (
            "Run only in the isolated test Compose API"
        )
        admin.autocommit = True

        def new_database(label):
            name = f"cra_startup_{label}_{uuid.uuid4().hex[:10]}"
            with admin.cursor() as cur:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            created.append(name)
            return psycopg2.extensions.make_dsn(base, dbname=name)

        # Real independent connections contend on the same new, empty database.
        fresh = new_database("concurrent")
        application.DB_URL = fresh
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: application.init_db(deadline=time.monotonic() + 30), range(6)))
        assert snapshot(fresh) == {"releases": [], "components": [], "test_clock": []}
        checks.append("six concurrent initializers on empty schema")

        legacy = new_database("legacy")
        conn = connect(legacy)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE releases (release_id VARCHAR(64) PRIMARY KEY,
                        product VARCHAR(100) NOT NULL, version VARCHAR(50) NOT NULL,
                        support_end_date DATE NOT NULL, UNIQUE(product, version));
                    CREATE TABLE components (id SERIAL PRIMARY KEY,
                        release_id VARCHAR(64) REFERENCES releases(release_id) ON DELETE CASCADE,
                        name VARCHAR(100) NOT NULL, version VARCHAR(50) NOT NULL, purl TEXT);
                    CREATE TABLE test_clock (id INT PRIMARY KEY, now TIMESTAMPTZ);
                    INSERT INTO releases VALUES ('preserve-release', 'Router', '1', '2027-01-01');
                    INSERT INTO components (release_id, name, version, purl)
                        VALUES ('preserve-release', 'library', '2', 'pkg:generic/library@2');
                    INSERT INTO test_clock VALUES (1, '2026-11-01T23:59:59Z');
                """)
        finally:
            conn.close()
        before = snapshot(legacy)
        application.DB_URL = legacy
        application.init_db()
        assert snapshot(legacy) == before
        holder = connect(legacy)
        try:
            with holder, holder.cursor() as cur:
                cur.execute("LOCK TABLE releases, components IN ACCESS SHARE MODE")
                # An unnecessary ALTER TABLE would block on this held lock.
                application.init_db(deadline=time.monotonic() + 10)
                cur.execute("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_schema='public' AND (
                        (table_name='releases' AND column_name IN ('product','version')) OR
                        (table_name='components' AND column_name IN ('name','version')))
                """)
                assert [row["data_type"] for row in cur.fetchall()] == ["text"] * 4
        finally:
            holder.close()
        assert snapshot(legacy) == before
        checks.append("legacy VARCHAR upgrade and repeat startup preserve all rows/timestamps")
        checks.append("TEXT schema startup avoids exclusive ALTER locks")

        holder = connect(legacy)
        try:
            with holder, holder.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (application.SCHEMA_LOCK_KEY,))
                started = time.monotonic()
                try:
                    application.init_db(deadline=started + 5)
                except psycopg2.OperationalError:
                    pass
                else:
                    raise AssertionError("Contended startup must have a bounded lock wait")
                assert time.monotonic() - started < 8
        finally:
            holder.close()
        application.init_db()
        assert snapshot(legacy) == before
        checks.append("bounded advisory-lock timeout and subsequent recovery")

        # Query settings are per connection and do not alter server/user defaults.
        with (
            application.database(
                connect_timeout=2, statement_timeout_ms=1000, lock_timeout_ms=500, read_only=True
            ) as conn,
            conn.cursor() as cur,
        ):
            cur.execute(
                "SELECT current_setting('default_transaction_read_only') AS read_only, "
                "current_setting('statement_timeout') AS statement_timeout, "
                "current_setting('lock_timeout') AS lock_timeout, "
                "current_setting('TimeZone') AS timezone"
            )
            row = cur.fetchone()
            assert dict(row) == {
                "read_only": "on",
                "statement_timeout": "1s",
                "lock_timeout": "500ms",
                "timezone": "UTC",
            }
        checks.append("readiness connection is read-only, UTC and timeout bounded")

        incompatible = new_database("incompatible")
        conn = connect(incompatible)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE releases (release_id VARCHAR(64) PRIMARY KEY, "
                    "product INTEGER NOT NULL, version TEXT NOT NULL, "
                    "support_end_date DATE NOT NULL)"
                )
                cur.execute("INSERT INTO releases VALUES ('keep', 7, '1', '2027-01-01')")
        finally:
            conn.close()
        application.DB_URL = incompatible
        try:
            application.init_db()
        except RuntimeError as exc:
            assert "manual migration" in str(exc)
        else:
            raise AssertionError("Unexpected schema types must fail without conversion")
        conn = connect(incompatible)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT product FROM releases")
                assert cur.fetchone()["product"] == 7
                cur.execute("SELECT to_regclass('public.components') AS table_name")
                assert cur.fetchone()["table_name"] is None  # DDL was rolled back.
                cur.execute(
                    "SELECT pg_try_advisory_xact_lock(%s) AS acquired",
                    (application.SCHEMA_LOCK_KEY,),
                )
                assert cur.fetchone()["acquired"] is True
        finally:
            conn.close()
        checks.append("incompatible schema fails closed; DDL rolls back and advisory lock releases")
        print(
            json.dumps(
                {"status": "passed", "checks": checks, "created_test_databases_retained": created},
                indent=2,
            )
        )
    finally:
        application.DB_URL = base
        admin.close()


if __name__ == "__main__":
    main()
