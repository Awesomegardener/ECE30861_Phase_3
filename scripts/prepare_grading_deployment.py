"""Render exact Cloud Run candidate commands, never execute cloud operations.

Image digests must come from paired approved builds at the same source commit.
Existing SQL attachments, DSN secret references, identities, probes and IAM are
preserved by update flags; verify them before executing the generated commands.
"""

import argparse
import json
import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commands(config, system_digest, tester_digest):
    for digest in (system_digest, tester_digest):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ValueError("Require actual sha256 image digests from approved paired builds")
    result = {}
    for role, digest in (("system", system_digest), ("tester", tester_digest)):
        service = config[role]
        args = [
            "gcloud",
            "run",
            "services",
            "update",
            service["service"],
            "--project=" + config["project"],
            "--region=" + config["region"],
            "--image=" + service["repository"] + "@" + digest,
            "--no-traffic",
            "--tag=autograder-review",
            "--cpu-throttling",
            "--command=" + service["command"],
            "--args=" + service["args"],
            "--concurrency=" + service["concurrency"],
            "--update-env-vars=" + ",".join(k + "=" + v for k, v in service["environment"].items()),
        ]
        args += ["--" + k + "=" + v for k, v in config["resources"].items()]
        result[role] = shlex.join(args)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-digest", required=True)
    parser.add_argument("--tester-digest", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/deployment-review")
    args = parser.parse_args()
    config = json.loads((ROOT / "deploy/grading-config.json").read_text())
    rendered = commands(config, args.system_digest, args.tester_digest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for role, command in rendered.items():
        path = args.output_dir / (role + "-candidate.sh")
        path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            "# Execute only after deployment approval and secret/IAM/storage review.\n"
            + command
            + "\n"
        )
        print(path)


if __name__ == "__main__":
    main()
