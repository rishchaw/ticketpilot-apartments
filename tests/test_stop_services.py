"""Stopping local workloads must not prevent the independent cloud pause."""
import json
from pathlib import Path
from types import SimpleNamespace
from scripts import stop_services


def test_docker_already_offline_is_idempotent_and_does_not_start_it(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_services, "ROOT", tmp_path)
    monkeypatch.setattr(stop_services.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=1, stderr="The system cannot find the file specified"))
    def no_commands(*args, **kwargs):
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
    def checked(command, log, **kwargs):
        calls.append(command)
        return {"stopped": command[0] != "docker"}
    monkeypatch.setattr(stop_services, "checked", checked)
    assert stop_services.main(["--project", "project-demo-123"]) == 1
    assert len(calls) == 2
    assert calls[-1][-2:] == ["--stage", "pause"]


def stop_fixture(monkeypatch, tmp_path, *, aws=True, gcp=True):
    monkeypatch.setattr(stop_services, "ROOT", tmp_path)
    monkeypatch.setattr(stop_services.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stderr=""))
    tools = tmp_path / ".tools"
    tools.mkdir()
    if aws is not None:
        (tools / "aws-deployment.json").write_text(json.dumps({"deployed": aws}), encoding="utf-8")
    if gcp:
        (tools / "gcp-deployment.json").write_text(json.dumps({"project": "project-demo-123"}), encoding="utf-8")
    calls = []
    def checked(command, log, **kwargs):
        calls.append(command)
        return {"stopped": True}
    monkeypatch.setattr(stop_services, "checked", checked)
    return tools, calls


def test_default_stops_both_known_clouds_after_local_failure(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    def checked(command, log, **kwargs):
        calls.append(command)
        return {"stopped": command[0] != "docker" and "scripts/deploy_gcp.py" not in command}
    monkeypatch.setattr(stop_services, "checked", checked)
    assert stop_services.main([]) == 1
    scripts = [command[1] for command in calls if command[0] != "docker"]
    assert scripts == ["scripts/deploy_gcp.py", "scripts/deploy_aws.py"]
    aws = calls[-1]
    assert aws[-4:] == ["--stage", "pause", "--profile", "ticketpilot"]
    assert "--region" not in aws
    report = json.loads((tools / "stop-services.json").read_text())
    assert report["aws"]["stopped"] and not report["gcp"]["stopped"]
    assert all(name in report["data"] for name in ("DynamoDB", "Firestore", "Compose"))


def test_explicit_aws_pauses_without_deployment_record_and_ignores_gcp(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path, aws=None)
    assert stop_services.main(["--provider", "aws", "--profile", "ticketpilot"]) == 0
    assert len(calls) == 2 and "scripts/deploy_aws.py" in calls[-1]
    assert all("scripts/deploy_gcp.py" not in command for command in calls)
    assert "skipped" in json.loads((tools / "stop-services.json").read_text())["gcp"]


def test_gcp_only_does_not_contact_known_aws(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    assert stop_services.main(["--provider", "gcp"]) == 0
    assert len(calls) == 2 and "scripts/deploy_gcp.py" in calls[-1]
    assert all("scripts/deploy_aws.py" not in command for command in calls)
    assert "skipped" in json.loads((tools / "stop-services.json").read_text())["aws"]


def test_local_only_contacts_neither_cloud_even_when_both_are_known(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    assert stop_services.main(["--local-only"]) == 0
    assert len(calls) == 1 and calls[0][0] == "docker"
    report = json.loads((tools / "stop-services.json").read_text())
    assert "skipped" in report["aws"] and "skipped" in report["gcp"]


def test_default_skips_aws_unless_deployed_is_boolean_true(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path, aws="true", gcp=False)
    assert stop_services.main([]) == 0
    assert len(calls) == 1 and calls[0][0] == "docker"
    assert "skipped" in json.loads((tools / "stop-services.json").read_text())["aws"]


def test_bad_gcp_record_does_not_block_known_aws_pause(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    (tools / "gcp-deployment.json").write_text("{broken", encoding="utf-8")
    assert stop_services.main([]) == 1
    assert "scripts/deploy_aws.py" in calls[-1]
    report = json.loads((tools / "stop-services.json").read_text())
    assert report["gcp"]["error"] == "JSONDecodeError" and report["aws"]["stopped"]
    assert "{broken" not in json.dumps(report)


def test_bad_aws_record_does_not_block_gcp_pause(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    (tools / "aws-deployment.json").write_text("{broken", encoding="utf-8")
    assert stop_services.main([]) == 1
    assert any("scripts/deploy_gcp.py" in command for command in calls)
    report = json.loads((tools / "stop-services.json").read_text())
    assert report["aws"]["error"] == "JSONDecodeError" and report["gcp"]["stopped"]


def test_unexpected_stop_exception_does_not_block_other_cloud(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    def checked(command, log, **kwargs):
        calls.append(command)
        if command[0] == "docker":
            raise OSError("synthetic local failure")
        if "scripts/deploy_gcp.py" in command:
            raise RuntimeError("synthetic GCP failure")
        return {"stopped": True}
    monkeypatch.setattr(stop_services, "checked", checked)
    assert stop_services.main([]) == 1
    assert "scripts/deploy_aws.py" in calls[-1]
    report = json.loads((tools / "stop-services.json").read_text())
    assert report["docker_compose"]["error"] == "OSError"
    assert report["gcp"]["error"] == "RuntimeError" and report["aws"]["stopped"]


def test_compose_stop_without_env_uses_scoped_placeholders_only(monkeypatch, tmp_path):
    tools, calls = stop_fixture(monkeypatch, tmp_path)
    assert not (tmp_path / ".env").exists()
    original = {"ADMIN_TOKEN": "original-test-owner", "METRICS_TOKEN": "original-test-metrics", "GRAFANA_ADMIN_PASSWORD": "original-test-grafana"}
    for name, value in original.items():
        monkeypatch.setenv(name, value)
    observed = []
    def checked(command, log, **kwargs):
        observed.append((command, kwargs.get("env")))
        return {"stopped": True}
    monkeypatch.setattr(stop_services, "checked", checked)
    assert stop_services.main([]) == 0
    compose = next(environment for command, environment in observed if command[0] == "docker")
    for name, value in original.items():
        assert compose[name] == "unused-only-for-compose-stop" and compose[name] != value
        assert stop_services.os.environ[name] == value
    cloud = [(command, environment) for command, environment in observed if command[0] != "docker"]
    assert len(cloud) == 2 and all(environment is None for command, environment in cloud)
    assert all("--stage" in command and "pause" in command for command, environment in cloud)


def test_checked_passes_only_the_requested_process_environment(monkeypatch, tmp_path):
    captured = []
    def run(command, **kwargs):
        captured.append(kwargs.get("env"))
        return SimpleNamespace(returncode=0, stdout="synthetic stop complete", stderr="")
    monkeypatch.setattr(stop_services, "ROOT", tmp_path)
    monkeypatch.setattr(stop_services.subprocess, "run", run)
    scoped = {"ADMIN_TOKEN": "unused-only-for-compose-stop"}
    assert stop_services.checked(["docker", "compose", "stop"], tmp_path / ".tools/compose.log", env=scoped)["stopped"]
    assert stop_services.checked(["python", "scripts/deploy_aws.py", "--stage", "pause"], tmp_path / ".tools/aws.log")["stopped"]
    assert captured == [scoped, None]
