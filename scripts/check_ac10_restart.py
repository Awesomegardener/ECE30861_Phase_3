"""AC-10 two-step restart persistence check (pod Phase 5 Q6).

Step 1 (tester): ``seed`` resets the target, sets the clock, creates releases,
SBOM components, a mandatory incident with a fix, a submission, report data for
every stage and the resulting audit events, then saves a JSON snapshot.
Step 2 (owner): restart the service process without a reset.
Step 3 (tester): ``verify`` sets the same clock, re-reads every record and
requires an exact match: 100% retention and 0-second timestamp drift.

Example:
    python scripts/check_ac10_restart.py seed --base-url URL --allow-reset --snapshot s.json
    docker compose -f cra-service/docker-compose.test.yml restart api
    python scripts/check_ac10_restart.py verify --base-url URL --snapshot s.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CLOCK = "2026-11-03T12:00:00Z"
USER = {"X-User-Id": "ac10-tester"}


def api(base):
    base = base.rstrip("/")
    return base if base.endswith("/api/v1") else base + "/api/v1"


def call(session, method, url, status, **kwargs):
    response = session.request(method, url, timeout=15, **kwargs)
    if response.status_code != status:
        sys.exit(
            f"{method} {url} returned {response.status_code}, expected {status}: {response.text}"
        )
    return response.json() if response.content else None


def read_state(session, base, ids):
    state = {
        "releases": [
            call(session, "GET", f"{base}/releases/{rid}", 200) for rid in ids["releases"]
        ],
        "components": [
            call(session, "GET", f"{base}/releases/{rid}/components", 200)
            for rid in ids["releases"]
        ],
        "incident": call(session, "GET", f"{base}/incidents/{ids['incident']}", 200),
        "reports": {
            stage: call(session, "GET", f"{base}/incidents/{ids['incident']}/reports/{stage}", 200)
            for stage in ("early_warning", "vulnerability_notification", "final_report")
        },
        "audit_logs": call(session, "GET", f"{base}/audit-logs", 200),
    }
    for item in state["components"]:
        # Component order is not promised by the contract; compare as a multiset.
        item["components"] = sorted(item["components"], key=lambda c: json.dumps(c, sort_keys=True))
    return state


def seed(args):
    if not args.allow_reset:
        sys.exit("seed resets the target; pass --allow-reset only for a coordinated target")
    base = api(args.base_url)
    session = requests.Session()
    session.headers.update(USER)
    call(session, "POST", f"{base}/test/reset", 204)
    call(session, "PUT", f"{base}/test/clock", 200, json={"now": CLOCK})
    sbom = json.loads((ROOT / "fixtures/sbom_25_components.json").read_text(encoding="utf-8"))
    releases = []
    for version, end in (("1.0", "2026-11-03"), ("0.9", "2026-11-02")):
        release = call(
            session,
            "POST",
            f"{base}/releases",
            201,
            json={"product": "AC10Router", "version": version, "support_end_date": end},
        )
        releases.append(release["release_id"])
    call(session, "PUT", f"{base}/releases/{releases[0]}/sbom", 200, json=sbom)
    incident = call(
        session,
        "POST",
        f"{base}/incidents",
        201,
        json={
            "awareness_at": "2026-11-02T08:15:30.123456Z",
            "classification": "mandatory",
            "rationale": "AC-10 persistence check",
            "cve_id": "CVE-2026-10010",
        },
    )["incident_id"]
    call(
        session,
        "PATCH",
        f"{base}/incidents/{incident}",
        200,
        json={"fix_available_at": "2026-11-03T09:00:00Z"},
    )
    call(
        session,
        "POST",
        f"{base}/incidents/{incident}/submissions",
        201,
        json={"stage": "early_warning", "submitted_at": "2026-11-02T20:00:00Z"},
    )
    call(
        session,
        "PUT",
        f"{base}/incidents/{incident}/report-data/early_warning",
        200,
        json={"member_states": ["DE", "NL"]},
    )
    call(
        session,
        "PUT",
        f"{base}/incidents/{incident}/report-data/vulnerability_notification",
        200,
        json={"product_information": "AC10Router 1.0", "exploit_nature": "Remote"},
    )
    ids = {"releases": releases, "incident": incident}
    snapshot = {"clock": CLOCK, "ids": ids, "state": read_state(session, base, ids)}
    args.snapshot.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    events = len(snapshot["state"]["audit_logs"]["events"])
    print(f"Seeded and saved snapshot with {events} audit events to {args.snapshot}")


def wait_ready(base_url, timeout):
    root = base_url.rstrip("/").removesuffix("/api/v1")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if requests.get(root + "/health/ready", timeout=5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    sys.exit("Target did not become ready after restart")


def verify(args):
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    wait_ready(args.base_url, args.ready_timeout)
    base = api(args.base_url)
    session = requests.Session()
    session.headers.update(USER)
    # Same reference clock, so support status and generated_at are comparable.
    call(session, "PUT", f"{base}/test/clock", 200, json={"now": snapshot["clock"]})
    after = read_state(session, base, snapshot["ids"])
    before = snapshot["state"]
    differences = [key for key in before if before[key] != after[key]]
    if differences:
        sys.exit(f"AC-10 FAILED: state changed across restart in {differences}")
    events = len(after["audit_logs"]["events"])
    components = sum(len(item["components"]) for item in after["components"])
    print(
        f"AC-10 passed: {len(after['releases'])} releases, {components} components, 1 incident, "
        f"3 stage reports and {events} audit events identical after restart"
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="step", required=True)
    for name in ("seed", "verify"):
        step = sub.add_parser(name)
        step.add_argument("--base-url", required=True)
        step.add_argument("--snapshot", type=Path, default=ROOT / "artifacts/ac10-snapshot.json")
        if name == "seed":
            step.add_argument("--allow-reset", action="store_true")
        else:
            step.add_argument("--ready-timeout", type=float, default=120)
    args = parser.parse_args()
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    seed(args) if args.step == "seed" else verify(args)


if __name__ == "__main__":
    main()
