"""Report evidence for synthetic HTTP tests; not part of the deployed application."""

import datetime
import hashlib
import json
import re
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SAFE_HEADERS = {"content-type", "x-user-id", "x-request-id"}
SENSITIVE_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "authorization",
    "cookie",
    "databaseurl",
    "privatekey",
)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_url(value):
    parts = urlsplit(value)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc.rsplit("@", 1)[-1],
            parts.path,
            "[REDACTED]" if parts.query else "",
            "",
        )
    )


def redact_text(value):
    value = re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@", r"\1[REDACTED]@", value)
    value = re.sub(r"(?i)\bBearer\s+[^\s\"']+", "Bearer [REDACTED]", value)
    return re.sub(
        r"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+",
        r"\1[REDACTED]",
        value,
    )


def redact_json(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(term in re.sub(r"[^a-z]", "", key.lower()) for term in SENSITIVE_KEYS)
            else redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def body_evidence(value, limit):
    if value is None or value == b"" or value == "":
        return {"kind": "empty", "bytes": 0}
    if not isinstance(value, (str, bytes)):
        return {"kind": "unavailable", "reason": "Body is not buffered text or bytes"}
    raw = value.encode("utf-8") if isinstance(value, str) else value
    text = raw.decode("utf-8", errors="replace")
    metadata = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        parsed = json.loads(text)
        sanitized = redact_json(parsed)
        rendered = json.dumps(sanitized, ensure_ascii=True, allow_nan=False)
    except (ValueError, RecursionError):
        preview = redact_text(text)
        return {
            **metadata,
            "kind": "text",
            "text": preview[:limit],
            "truncated": len(preview) > limit,
        }
    if len(rendered) > limit:
        return {**metadata, "kind": "json", "preview": rendered[:limit], "truncated": True}
    return {**metadata, "kind": "json", "value": sanitized, "truncated": False}


def git_output(root, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def input_hashes(root):
    files = [root / "docs/openapi.yaml", *sorted((root / "fixtures").rglob("*"))]
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
        if path.is_file()
    }


class HttpEvidence:
    def __init__(
        self,
        root,
        directory,
        base_url,
        *,
        capture_bodies=False,
        body_limit=65536,
        tested_commit=None,
    ):
        self.directory = Path(directory)
        self.capture_bodies = capture_bodies
        self.body_limit = body_limit
        self.exchanges = []
        self.lock = threading.Lock()
        started = utc_now()
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.path = self.directory / f"http-evidence-{stamp}-{uuid.uuid4().hex[:8]}.json"
        status = git_output(root, "status", "--porcelain")
        source_files = [
            *sorted((root / "cra-service").glob("*.py")),
            *sorted((root / "cra-service").glob("requirements*.txt")),
            root / "cra-service/Dockerfile",
            root / "cra-service/docker-compose.test.yml",
        ]
        self.run = {
            "id": self.path.stem,
            "started_at_utc": started,
            "target_base_url": safe_url(base_url),
            "tested_commit_sha": tested_commit,
            "target_version_provenance": "operator supplied; not verified by the HTTP runner"
            if tested_commit
            else "unknown; supply --tested-commit or TESTED_COMMIT_SHA",
            "runner_commit_sha": git_output(root, "rev-parse", "HEAD"),
            "runner_worktree_dirty": bool(status) if status is not None else None,
            "runner_source_sha256": {
                path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source_files
                if path.is_file()
            },
            "shared_input_sha256": input_hashes(root),
            "bodies_captured": capture_bodies,
            "body_limit_characters": body_limit,
        }

    def record(self, observation, *, response=None, prepared=None, url=None):
        if response is not None:
            prepared = response.request
        request = {"url": safe_url(prepared.url if prepared is not None else url)}
        request["headers"] = {
            key: redact_text(value)
            for key, value in (prepared.headers.items() if prepared is not None else [])
            if key.lower() in SAFE_HEADERS
        }
        received = None
        if response is not None:
            received = {
                "headers": {
                    key: redact_text(value)
                    for key, value in response.headers.items()
                    if key.lower() in SAFE_HEADERS
                }
            }
        if self.capture_bodies:
            request["body"] = (
                body_evidence(prepared.body, self.body_limit)
                if prepared is not None
                else {"kind": "unavailable"}
            )
            if received is not None:
                received["body"] = body_evidence(response.content, self.body_limit)
        with self.lock:
            self.exchanges.append({**observation, "request": request, "response": received})

    def write(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run["completed_at_utc"] = utc_now()
        bundle = {"schema_version": 1, "run": self.run, "exchanges": self.exchanges}
        self.path.write_text(json.dumps(bundle, indent=2, allow_nan=False), encoding="utf-8")
        # Preserve the existing status-report input as a latest-run convenience.
        observations = [
            {key: value for key, value in entry.items() if key not in {"request", "response"}}
            for entry in self.exchanges
            if entry["status"] is not None
        ]
        (self.directory / "operation-observations.json").write_text(
            json.dumps(observations, indent=2), encoding="utf-8"
        )
        return self.path
