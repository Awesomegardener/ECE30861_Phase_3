"""Explicit deployment authorization for destructive acceptance checks."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

TEAM2 = "https://cra-phase3-api-456725640364.us-central1.run.app"
TEAM6 = "http://136.116.160.182:8080"
ROOT = Path(__file__).resolve().parents[2]
GRADING_DATABASE = "cra_grading"


def system_target():
    """Self-tests must reach this process, never a public/default remote system."""
    port = os.getenv("PORT", "8080")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535")
    return f"http://127.0.0.1:{int(port)}"


class HarnessError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def normalize_target(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise HarnessError(400, "INVALID_TARGET", "target_base_url must be an approved HTTP URL")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise HarnessError(400, "INVALID_TARGET", "Invalid target URL") from None
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path.rstrip("/") not in {"", "/api/v1"}
    ):
        raise HarnessError(400, "INVALID_TARGET", "Use an approved origin or its /api/v1 base")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    authority = host + (f":{port}" if port is not None else "")
    return urlunsplit((parts.scheme.lower(), authority, "", "", ""))


def session_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
        raise HarnessError(
            400, "INVALID_REQUEST", "session_id must contain 1-128 letters, digits, _, . or -"
        )
    return value


@dataclass
class Settings:
    role: str
    enabled: bool
    allow_reset: bool
    database_url: str
    default_target: str
    approved_targets: frozenset[str]
    reset_database: str
    timeout: int
    root: Path = ROOT

    @classmethod
    def environment(cls, role):
        default_target = system_target() if role == "system" else TEAM2
        default_approved = default_target if role == "system" else f"{TEAM2},{TEAM6}"
        timeout = int(os.getenv("AUTOGRADER_RUN_TIMEOUT_SECONDS", "600"))
        if not 1 <= timeout <= 1800:
            raise ValueError("AUTOGRADER_RUN_TIMEOUT_SECONDS must be between 1 and 1800")
        return cls(
            role=role,
            enabled=os.getenv("AUTOGRADER_ENABLED", "false").lower() == "true",
            allow_reset=os.getenv("AUTOGRADER_ALLOW_RESET", "false").lower() == "true",
            database_url=os.getenv("AUTOGRADER_DATABASE_URL", ""),
            default_target=normalize_target(os.getenv("AUTOGRADER_DEFAULT_TARGET", default_target)),
            approved_targets=frozenset(
                normalize_target(value)
                for value in os.getenv("AUTOGRADER_APPROVED_TARGETS", default_approved).split(",")
            ),
            reset_database=os.getenv("AUTOGRADER_RESET_DATABASE", ""),
            timeout=timeout,
        )

    def authorize(self, target=None):
        if not self.enabled or not self.database_url:
            raise HarnessError(503, "NOT_CONFIGURED", "Autograder controls are not configured")
        if self.role == "system" and self.default_target != system_target():
            raise HarnessError(
                503,
                "NOT_CONFIGURED",
                "System test target must be loopback at this container's PORT",
            )
        target = normalize_target(target if target is not None else self.default_target)
        if target not in self.approved_targets:
            raise HarnessError(400, "INVALID_TARGET", "Target is not explicitly approved")
        if self.role == "system" and target != self.default_target:
            raise HarnessError(400, "INVALID_TARGET", "System sessions can test only this system")
        if not self.allow_reset:
            raise HarnessError(
                503, "RESET_DISABLED", "Disposable-target reset authorization is disabled"
            )
        return target
