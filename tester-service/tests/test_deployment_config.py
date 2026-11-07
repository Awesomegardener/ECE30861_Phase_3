"""The reviewed grading profile must actually select the instrumented entrypoint."""

import json
import runpy
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
render = runpy.run_path(str(ROOT / "scripts/prepare_grading_deployment.py"))["commands"]


def test_candidate_commands_preserve_secrets_and_select_deployable_coverage():
    config = json.loads((ROOT / "deploy/grading-config.json").read_text())
    commands = render(config, "sha256:" + "a" * 64, "sha256:" + "b" * 64)
    for role, command in commands.items():
        args = shlex.split(command)
        assert "--no-traffic" in args and "--max=1" in args and "--max-instances=1" in args
        assert "--memory=1Gi" in args and "--timeout=900" in args
        assert not any(
            flag.startswith(
                ("--set-secrets", "--clear-secrets", "--env-vars-file", "--set-env-vars")
            )
            for flag in args
        )
        assert not any("AUTOGRADER_COVERAGE_TOKEN" in flag for flag in args)
        env = config[role]["environment"]
        if role == "system":
            assert env["AUTOGRADER_COVERAGE_ENABLED"] == "true"
        else:
            assert env["AUTOGRADER_SETUP_TIMEOUT_SECONDS"] == "60"
        assert int(config[role]["concurrency"]) >= 2
    assert "--args=-m,autograder.grading_server" in shlex.split(commands["system"])
    assert "cra-api-grading@sha256:" in commands["system"]
    assert "DATABASE_URL" not in config["tester"]["environment"]
    assert config["system"]["environment"]["AUTOGRADER_RESET_DATABASE"] == "cra_grading"


@pytest.mark.parametrize("digest", ["latest", "sha256:placeholder", "sha256:" + "a" * 63])
def test_missing_actual_build_digest_cannot_generate_deployment_command(digest):
    config = json.loads((ROOT / "deploy/grading-config.json").read_text())
    with pytest.raises(ValueError):
        render(config, digest, "sha256:" + "b" * 64)
