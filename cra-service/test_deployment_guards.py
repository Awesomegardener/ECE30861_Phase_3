"""Destructive test-control scope must never default to an existing app stack."""

import http.client

import pytest

from scripts.check_deployment_runtime import validate_project, wait_for_ready


@pytest.mark.parametrize(
    "project",
    [
        "",
        "cra-service",
        "cra-phase3-tests",
        "../cra-service",
        "--project",
        "cra-phase3-deployment-\nother",
    ],
)
def test_deployment_controls_refuse_unrelated_projects(project):
    with pytest.raises(ValueError):
        validate_project(project)


def test_deployment_controls_require_explicit_test_project():
    assert validate_project("cra-phase3-deployment-ci") == "cra-phase3-deployment-ci"


def test_ready_wait_retries_connection_closed_during_container_start(monkeypatch):
    attempts = []
    monkeypatch.setattr("scripts.check_deployment_runtime.time.sleep", lambda _: None)

    def check():
        attempts.append(True)
        if len(attempts) == 1:
            raise http.client.RemoteDisconnected("Container has not started listening")

    wait_for_ready(check)
    assert len(attempts) == 2
