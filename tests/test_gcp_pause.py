"""Pause controls must preserve data and reject unrelated infrastructure changes."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import deploy_gcp as deploy


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    monkeypatch.setattr(deploy, "TOOLS", tmp_path / ".tools")
    (tmp_path / ".tools").mkdir()
    (tmp_path / "infra/gcp/app").mkdir(parents=True)
    monkeypatch.setattr(deploy, "terraform", lambda: "terraform")
    return tmp_path


def service(paused=True):
    return {
        "scaling": [{"min_instance_count": 0, "max_instance_count": 1,
                     "scaling_mode": "MANUAL" if paused else "AUTOMATIC",
                     "manual_instance_count": 0 if paused else None}],
        "template": [{"scaling": [{"min_instance_count": 0, "max_instance_count": 1}],
                      "containers": [{"image": "unchanged@sha256:0000",
                                      "resources": [{"cpu_idle": True, "startup_cpu_boost": False}],
                                      "env": [{"name": "LLM_PROVIDER", "value": "none"},
                                              {"name": "STORAGE_MODE", "value": "firestore"}]}]}],
        "traffic": [{"percent": 100}], "ingress": "INGRESS_TRAFFIC_ALL",
        "deletion_protection": True, "labels": {"application": "ticketpilot"},
    }


def run_plan(monkeypatch, changes):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if "show" in command:
            return json.dumps({"resource_changes": changes})
        return "{}"
    monkeypatch.setattr(deploy, "run", run)
    return calls


def change(kind="google_cloud_run_v2_service", action=None):
    after = service()
    return {"address": kind + ".app", "type": kind,
            "change": {"actions": action or ["update"], "before": copy.deepcopy(after), "after": after}}


def test_pause_plan_allows_only_scaling_change(local, monkeypatch):
    item = change()
    item["change"]["before"]["scaling"] = service(False)["scaling"]
    calls = run_plan(monkeypatch, [item])
    deploy.plan_apply("app", {"paused": True}, scaling_only=True)
    assert any("apply" in command for command in calls)


@pytest.mark.parametrize("item", [
    change("google_firestore_database"),
    change(action=["delete"]),
    change(action=["create"]),
])
def test_pause_rejects_database_or_create_delete_actions(local, monkeypatch, item):
    calls = run_plan(monkeypatch, [item])
    with pytest.raises(RuntimeError):
        deploy.plan_apply("app", {"paused": True}, scaling_only=True)
    assert not any("apply" in command for command in calls)


def test_pause_cannot_change_image_or_runtime_identity(local, monkeypatch):
    item = change()
    item["change"]["after"]["template"][0]["containers"][0]["image"] = "unexpected-new-image"
    calls = run_plan(monkeypatch, [item])
    with pytest.raises(RuntimeError, match="cannot change service template"):
        deploy.plan_apply("app", {"paused": True}, scaling_only=True)
    assert not any("apply" in command for command in calls)


def test_generated_pause_state_survives_read_and_refuses_wrong_project(local):
    settings = {"project_id": "project-demo-123", "region": "asia-southeast1",
                "paused": True, "manage_database": True, "image_uri": "same-image"}
    deploy.tfvars(local / "infra/gcp/app", settings)
    args = SimpleNamespace(project="project-demo-123", region="asia-southeast1")
    assert deploy.app_settings(args) == settings
    args.project = "other-project-456"
    with pytest.raises(RuntimeError, match="different project"):
        deploy.app_settings(args)


@pytest.mark.parametrize("stage,expected", [("pause", True), ("resume", False)])
def test_pause_resume_does_not_need_billing_or_image_build(local, monkeypatch, stage, expected):
    observed = []
    monkeypatch.setattr(deploy, "change_pause_state", lambda args, paused: observed.append(paused))
    def no_billing(*args):
        raise AssertionError("Pause/resume should not require billing checks or image delivery")
    monkeypatch.setattr(deploy, "preflight", no_billing)
    assert deploy.main(["--project", "project-demo-123", "--stage", stage]) == 0
    assert observed == [expected]


def test_tagged_revision_urls_prevent_false_offline_claim(local, monkeypatch):
    monkeypatch.setattr(deploy, "cloud", lambda *args, **kwargs: {
        "metadata": {"annotations": {"run.googleapis.com/scalingMode": "manual",
                                     "run.googleapis.com/manualInstanceCount": "0"}},
        "status": {"traffic": [{"tag": "still-exposed"}]},
    })
    with pytest.raises(RuntimeError, match="Tagged revision"):
        deploy.verify_service_state(SimpleNamespace(region="asia-southeast1"), True, "https://example.run.app")


def test_existing_state_without_generated_settings_cannot_accidentally_resume(local):
    (local / "infra/gcp/app/terraform.tfstate").write_text("{}")
    args = SimpleNamespace(project="project-demo-123", region="asia-southeast1")
    with pytest.raises(RuntimeError, match="Restore"):
        deploy.app_settings(args)
