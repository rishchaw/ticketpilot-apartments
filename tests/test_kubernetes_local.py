"""Guard against foreign-cluster mutations and leaked demo credentials."""
import copy
import json
from pathlib import Path
import shutil
import pytest
import yaml
from scripts import kubernetes_local as demo


@pytest.fixture
def paths(tmp_path):
    source = Path(__file__).resolve().parents[1]
    for relative in [*(str(Path("deploy/kubernetes") / name) for name in demo.TEMPLATES), *demo.CONFIG_FILES.values()]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    return demo.DemoPaths(tmp_path)


def test_prepare_uses_separate_credentials_and_does_not_leak_them(paths):
    (paths.root / ".env").write_text("ADMIN_TOKEN=existing-real-data-access-code\n")
    state = demo.prepare(paths)
    secrets = json.loads(paths.credentials.read_text())
    assert set(secrets) == demo.CREDENTIAL_KEYS
    assert all(len(value) >= 32 and value != "existing-real-data-access-code" for value in secrets.values())
    rendered = "\n".join(p.read_text() for p in paths.rendered.rglob("*") if p.is_file())
    assert all(value not in rendered for value in secrets.values())
    assert not paths.kubeconfig.exists()
    assert demo.prepare(paths)["owner"] == state["owner"]
    assert json.loads(paths.credentials.read_text()) == secrets


def test_ownership_record_from_another_workspace_is_rejected(paths):
    demo.prepare(paths)
    state = json.loads(paths.ownership.read_text())
    state["workspace"] = "/some/other/project"
    paths.ownership.write_text(json.dumps(state))
    with pytest.raises(demo.LocalDemoError, match="does not match"):
        demo.load_ownership(paths)


def test_replaced_or_foreign_nodes_are_not_owned():
    state = {"node_ids": ["a" * 64]}
    good = {"Id": "a" * 64, "Config": {"Labels": {"io.x-k8s.kind.cluster": demo.CLUSTER}}}
    demo.verify_node_ownership(state, [good])
    replaced = copy.deepcopy(good)
    replaced["Id"] = "b" * 64
    with pytest.raises(demo.LocalDemoError, match="unowned/replaced"):
        demo.verify_node_ownership(state, [replaced])
    foreign = copy.deepcopy(good)
    foreign["Config"]["Labels"]["io.x-k8s.kind.cluster"] = "someone-else"
    with pytest.raises(demo.LocalDemoError):
        demo.verify_node_ownership(state, [foreign])


def test_remote_kubeconfig_cannot_target_cloud(paths):
    paths.work.mkdir(parents=True, exist_ok=True)
    value = {
        "current-context": demo.CONTEXT,
        "contexts": [{"name": demo.CONTEXT, "context": {"cluster": demo.CONTEXT, "user": demo.CONTEXT}}],
        "clusters": [{"name": demo.CONTEXT, "cluster": {"server": "https://127.0.0.1:6443", "certificate-authority-data": "YQ=="}}],
        "users": [{"name": demo.CONTEXT, "user": {"client-certificate-data": "YQ==", "client-key-data": "YQ=="}}],
    }
    paths.kubeconfig.write_text(yaml.safe_dump(value))
    assert demo.validate_kubeconfig(paths).hostname == "127.0.0.1"
    value["clusters"][0]["cluster"]["server"] = "https://production.example.com:6443"
    paths.kubeconfig.write_text(yaml.safe_dump(value))
    with pytest.raises(demo.LocalDemoError, match="non-loopback"):
        demo.validate_kubeconfig(paths)


def test_private_update_failure_preserves_existing_valid_metadata(paths, monkeypatch):
    demo.prepare(paths)
    old = paths.ownership.read_bytes()
    def interrupted(*args):
        raise OSError("Interrupted before atomic rename")
    monkeypatch.setattr(demo.os, "replace", interrupted)
    with pytest.raises(OSError):
        demo._write_private(paths.ownership, {"changed": True}, paths)
    assert paths.ownership.read_bytes() == old
    assert not list(paths.work.glob("*.tmp-*"))


def test_namespace_without_matching_owner_is_rejected():
    state = {"owner": "a" * 32}
    value = {"metadata": {"name": demo.NAMESPACE,
             "labels": {demo.PART_OF_LABEL: "ticketpilot", demo.PURPOSE_LABEL: "portfolio-demo", demo.OWNER_LABEL: "b" * 32}}}
    with pytest.raises(demo.LocalDemoError, match="ownership"):
        demo.verify_namespace(state, value)


def test_kind_bootstrap_uses_only_custom_node_label_domains(paths):
    demo.prepare(paths)
    config = yaml.safe_load((paths.rendered / "kind.yaml").read_text())
    labels = config["nodes"][0]["labels"]
    assert labels and all(key.startswith("ticketpilot.local/") for key in labels)
