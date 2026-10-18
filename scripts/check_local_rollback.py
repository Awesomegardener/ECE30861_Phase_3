"""Run inside the isolated test API container; never against application data."""

import json
import os
import urllib.error
import urllib.request
import uuid
from collections import Counter

import psycopg2


def request(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        "http://127.0.0.1:8080/api/v1" + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "X-User-Id": "local-rollback-check"},
    )
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        # This internal regression check is distinct from the portable HTTP suite.
        assert conn.get_dsn_parameters()["dbname"] == "cra_test", "Dedicated test DB required"
        assert conn.get_dsn_parameters()["host"] == "db", "Run in the dedicated test Compose API"
        token = uuid.uuid4().hex[:12]
        function = "rollback_check_" + token
        failure_name = "forced_failure_" + token
        code, release = request(
            "POST",
            "/releases",
            {"product": "RollbackCheck", "version": token, "support_end_date": "2027-01-01"},
        )
        assert code == 201
        path = "/releases/" + release["release_id"]
        bom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "library", "name": f"original-{i}", "version": "1"} for i in range(25)
            ],
        }
        assert request("PUT", path + "/sbom", bom)[0] == 200
        before = request("GET", path + "/components")[1]["components"]
        try:
            with conn, conn.cursor() as cur:
                # Names are generated hex tokens; identifier/value adaptation remains explicit.
                from psycopg2 import sql

                cur.execute(
                    sql.SQL(
                        "CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                        "BEGIN IF NEW.name = {} THEN RAISE EXCEPTION 'isolated rollback check'; "
                        "END IF; RETURN NEW; END $$"
                    ).format(sql.Identifier(function), sql.Literal(failure_name))
                )
                cur.execute(
                    sql.SQL(
                        "CREATE TRIGGER {} BEFORE INSERT ON components FOR EACH ROW EXECUTE FUNCTION {}()"
                    ).format(sql.Identifier(function), sql.Identifier(function))
                )
            bom["components"][-1]["name"] = failure_name
            replacement = {
                **bom,
                "components": [
                    {
                        "type": "application",
                        "name": "replacement-parent",
                        "version": "2",
                        "components": bom["components"],
                    }
                ],
            }
            code, error = request("PUT", path + "/sbom", replacement)
            assert code == 500 and error["error"]["code"] == "DATABASE_ERROR"
            after = request("GET", path + "/components")[1]["components"]
            assert Counter(tuple(sorted(c.items())) for c in before) == Counter(
                tuple(sorted(c.items())) for c in after
            )
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = 'cra_test' "
                    "AND state = 'idle in transaction' AND pid <> pg_backend_pid()"
                )
                assert cur.fetchone()[0] == 0
            print(
                "PASS: injected final nested INSERT failure; 25 prior components retained; "
                "JSON 500; no idle transactions."
            )
        finally:
            with conn, conn.cursor() as cur:
                from psycopg2 import sql

                cur.execute(
                    sql.SQL("DROP TRIGGER IF EXISTS {} ON components").format(
                        sql.Identifier(function)
                    )
                )
                cur.execute(
                    sql.SQL("DROP FUNCTION IF EXISTS {}()").format(sql.Identifier(function))
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
