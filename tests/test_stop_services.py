"""Stopping local workloads must not prevent the independent cloud pause."""
import json
from pathlib import Path
from types import SimpleNamespace
from scripts import stop_services


def test_docker_already_offline_is_idempotent_and_does_not_start_it(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_services, "ROOT", tmp_path)
    monkeypatch.setattr(stop_services.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=1, stderr="The system cannot find the file specified"))
    def no_commands(*args):
        raise AssertionError("An offline local engine should not be started or mutated")
    monkeypatch.setattr(stop_services, "checked", no_commands)
    assert stop_services.main(["--local-only"]) == 0
    report = json.loads((tmp_path / ".tools/stop-services.json").read_text())
    assert report["docker_compose"]["stopped"]
    assert report["kubernetes_demo"]["stopped"]
    assert "skipped" in report["gcp"]


def test_local_stop_failure_still_attempts_cloud_pause(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_services, "ROOT", tmp_path)
    monkeypatch.setattr(stop_services.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stderr=""))
    calls = []
    def checked(command, log):
        calls.append(command)
        return {"stopped": command[0] != "docker"}
    monkeypatch.setattr(stop_services, "checked", checked)
    assert stop_services.main(["--project", "project-demo-123"]) == 1
    assert len(calls) == 2
    assert calls[-1][-2:] == ["--stage", "pause"]
