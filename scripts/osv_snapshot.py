"""Operator CLI: fetch official OSV data; explicitly import into a chosen DB.

No public ingestion endpoint, hidden network lookup or automatic DB reset.
"""

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cra-service"))
import osv_source  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def download(url):
    if not osv_source.source_url_allowed(url):
        raise ValueError("Only official OSV HTTPS origins are allowed")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(
        urllib.request.Request(url, headers={"User-Agent": "Team2-CRA-OSV/1"}), timeout=30
    ) as response:
        if response.status != 200:
            raise ValueError("OSV download did not return 200")
        chunks, size = [], 0
        while chunk := response.read(65536):
            size += len(chunk)
            if size > 64 * 1024 * 1024:
                raise ValueError("OSV download exceeds 64 MiB")
            chunks.append(chunk)
        return b"".join(chunks)


def fetch(*, identifier=None, ecosystem=None):
    if identifier is not None:
        if not re.fullmatch(r"[A-Za-z0-9:_.-]+", identifier):
            raise ValueError("Invalid OSV record identifier")
        url = "https://api.osv.dev/v1/vulns/" + identifier
        upstream = download(url)
        records = [json.loads(upstream)]
        scope = "selected-record:" + identifier
    else:
        if not ecosystem or not re.fullmatch(r"[A-Za-z0-9._-]+", ecosystem):
            raise ValueError("Use an OSV ecosystem directory name such as PyPI")
        url = "https://storage.googleapis.com/osv-vulnerabilities/" + ecosystem + "/all.zip"
        upstream = download(url)
        records, expanded = [], 0
        with zipfile.ZipFile(io.BytesIO(upstream)) as archive:
            for item in archive.infolist():
                if item.is_dir() or not item.filename.endswith(".json"):
                    continue
                expanded += item.file_size
                if (
                    item.file_size > 2 * 1024 * 1024
                    or expanded > 256 * 1024 * 1024
                    or len(records) >= 50000
                ):
                    raise ValueError("OSV archive exceeds bounded import limits")
                # Read bytes only; never extract paths from an untrusted ZIP.
                records.append(json.loads(archive.read(item)))
        scope = "ecosystem:" + ecosystem
    bundle = dict(
        format="team2-osv-snapshot-v1",
        source_url=url,
        scope=scope,
        fetched_at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        upstream_sha256=hashlib.sha256(upstream).hexdigest(),
        records=records,
    )
    raw = (json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf8")
    digest = hashlib.sha256(raw).hexdigest()
    osv_source.validate_bundle(raw, digest)
    return raw, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("fetch")
    source = get.add_mutually_exclusive_group(required=True)
    source.add_argument("--id", dest="identifier")
    source.add_argument("--ecosystem")
    get.add_argument("--output", type=Path, required=True)
    put = commands.add_parser("import")
    put.add_argument("--snapshot", type=Path, required=True)
    put.add_argument("--sha256", required=True)
    put.add_argument("--database-name", required=True)
    put.add_argument("--allow-import", action="store_true")
    commands.add_parser("inspect")
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            raw, digest = fetch(identifier=args.identifier, ecosystem=args.ecosystem)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as stream:
                stream.write(raw)
            print(json.dumps(dict(file=str(args.output), sha256=digest)))
        elif args.command == "import":
            if not args.allow_import:
                raise ValueError("Explicit --allow-import is required")
            if args.snapshot.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("Snapshot is too large")
            from main import database

            print(
                json.dumps(
                    osv_source.import_snapshot(
                        database, args.snapshot.read_bytes(), args.sha256, args.database_name
                    )
                )
            )
        else:
            from main import database

            with database(read_only=True) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT s.* FROM osv_active a JOIN osv_snapshots s USING(snapshot_id) WHERE a.id=1"
                )
                row = cur.fetchone()
            print(json.dumps(dict(row) if row else None, default=str))
    except Exception as exc:
        # PostgreSQL/transport exception text can contain private infrastructure.
        message = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Operation failed; inspect active snapshot metadata before retrying"
        )
        print(f"{type(exc).__name__}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
