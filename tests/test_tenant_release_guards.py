"""An old public portal must never be resumed using tenant-login deployment tools."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from scripts import deploy_aws as aws
from scripts import deploy_gcp as gcp

ACCOUNT = "123456789012"
AWS_IMAGE = ACCOUNT + ".dkr.ecr.ap-southeast-1.amazonaws.com/ticketpilot-aws@sha256:" + "a" * 64
OTHER_AWS_IMAGE = AWS_IMAGE[:-64] + "b" * 64
PROJECT = "project-demo-123"
GCP_IMAGE = "asia-southeast1-docker.pkg.dev/" + PROJECT + "/ticketpilot-apartments/app@sha256:" + "a" * 64
LOCAL_IMAGE = "sha256:" + "c" * 64


def aws_commands(root):
    return SimpleNamespace(root=root, args=SimpleNamespace(reserved_concurrency=None),
        aws=lambda *a, **k: {"AccountLimit": {"UnreservedConcurrentExecutions": 10}})


def aws_settings(root, *, paused=True):
    value = {"region": aws.REGION, "image_uri": AWS_IMAGE, "paused": paused, "reserved_concurrency": -1}
    aws.private_write(aws.settings_path(root, "app"), "".join(k + " = " + json.dumps(v) + "\n" for k, v in value.items()))
    return value


@pytest.mark.parametrize("problem", ["absent", "stale-proof", "live-drift", "boolean-proof"])
def test_aws_legacy_or_mismatched_release_is_refused_before_any_apply(monkeypatch, tmp_path, problem):
    commands = aws_commands(tmp_path)
    values = aws_settings(tmp_path)
    if problem != "absent":
        aws.record_applied(commands, ACCOUNT, values, {}, tenant_auth_release=1)
        path = tmp_path / ".tools/aws-deployment.json"
        proof = json.loads(path.read_text())
        if problem == "stale-proof": proof["image_uri"] = OTHER_AWS_IMAGE
        if problem == "boolean-proof": proof["tenant_auth_release"] = True
        path.write_text(json.dumps(proof))
    live = OTHER_AWS_IMAGE if problem == "live-drift" else AWS_IMAGE
    monkeypatch.setattr(aws, "current_function", lambda _: {"Code": {"ResolvedImageUri": live}})
    monkeypatch.setattr(aws, "plan_apply", lambda *a, **k: pytest.fail("Unsafe resume must not apply Terraform"))
    before = aws.settings_path(tmp_path, "app").read_bytes()
    with pytest.raises(aws.DeploymentError, match="tenant-login release"):
        aws.change_pause(commands, ACCOUNT, False)
    assert aws.settings_path(tmp_path, "app").read_bytes() == before


@pytest.mark.parametrize("has_proof,paused", [(False, True), (True, True), (True, False)])
def test_aws_pause_always_allowed_and_valid_resume_preserves_existing_proof(monkeypatch, tmp_path, has_proof, paused):
    commands = aws_commands(tmp_path)
    values = aws_settings(tmp_path, paused=not paused)
    if has_proof: aws.record_applied(commands, ACCOUNT, values, {}, tenant_auth_release=1)
    monkeypatch.setattr(aws, "current_function", lambda _: {"Code": {"ResolvedImageUri": AWS_IMAGE}})
    monkeypatch.setattr(aws, "current_concurrency", lambda _: 0)
    calls = []
    monkeypatch.setattr(aws, "plan_apply", lambda *a, **k: calls.append(copy.deepcopy(a[2])) or {})
    monkeypatch.setattr(aws, "observe", lambda *a, **k: json.loads((tmp_path / ".tools/aws-deployment.json").read_text()))
    report = aws.change_pause(commands, ACCOUNT, paused)
    assert len(calls) == 1 and calls[0]["paused"] is paused
    assert report["tenant_auth_release"] == int(has_proof)


def test_aws_generic_observation_cannot_invent_or_transfer_auth_proof(monkeypatch, tmp_path):
    commands = aws_commands(tmp_path)
    commands.aws = lambda *a, **k: {"FunctionUrl": "https://abcde.lambda-url.ap-southeast-1.on.aws/"}
    monkeypatch.setattr(aws, "current_function", lambda _: {"Code": {"ResolvedImageUri": AWS_IMAGE}, "Configuration": {"Environment": {"Variables": {"LLM_PROVIDER": "none"}}}})
    monkeypatch.setattr(aws, "current_concurrency", lambda _: 0)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(lambda _: httpx.Response(429)), **kw))
    assert aws.observe(commands, ACCOUNT)["tenant_auth_release"] == 0
    aws.record_applied(commands, ACCOUNT, aws_settings(tmp_path), {}, tenant_auth_release=1)
    assert aws.observe(commands, ACCOUNT)["tenant_auth_release"] == 1
    path = tmp_path / ".tools/aws-deployment.json"
    value = json.loads(path.read_text());value["image_uri"] = OTHER_AWS_IMAGE;path.write_text(json.dumps(value))
    assert aws.observe(commands, ACCOUNT)["tenant_auth_release"] == 0


@pytest.fixture
def gcp_local(monkeypatch, tmp_path):
    monkeypatch.setattr(gcp, "ROOT", tmp_path)
    monkeypatch.setattr(gcp, "TOOLS", tmp_path / ".tools")
    (tmp_path / ".tools").mkdir()
    folder = tmp_path / "infra/gcp/app";folder.mkdir(parents=True)
    args = SimpleNamespace(project=PROJECT, region="asia-southeast1", local_image="mutable:tag")
    gcp.tfvars(folder, {"project_id": PROJECT, "region": args.region, "image_uri": GCP_IMAGE, "paused": True})
    (folder / "terraform.tfstate").write_text("{}")
    return tmp_path, args


def gcp_proof(root, *, image=GCP_IMAGE, release=1):
    path = root / ".tools/gcp-deployment.json"
    path.write_text(json.dumps({"project": PROJECT, "region": "asia-southeast1", "image": image, "tenant_auth_release": release}))


@pytest.mark.parametrize("problem", ["absent", "stale", "boolean"])
def test_gcp_legacy_resume_is_refused_before_terraform_or_settings_change(gcp_local, monkeypatch, problem):
    root, args = gcp_local
    if problem != "absent":gcp_proof(root, image=GCP_IMAGE[:-64] + "b" * 64 if problem == "stale" else GCP_IMAGE, release=True if problem == "boolean" else 1)
    monkeypatch.setattr(gcp, "plan_apply", lambda *a, **k: pytest.fail("Old public release must never resume"))
    before = (root / "infra/gcp/app/ticketpilot.generated.tfvars").read_bytes()
    with pytest.raises(RuntimeError, match="tenant-login release"):
        gcp.change_pause_state(args, False)
    assert (root / "infra/gcp/app/ticketpilot.generated.tfvars").read_bytes() == before


@pytest.mark.parametrize("has_proof,paused", [(False, True), (True, True), (True, False)])
def test_gcp_pause_does_not_require_proof_and_valid_resume_uses_only_public_smoke(gcp_local, monkeypatch, has_proof, paused):
    root, args = gcp_local
    if has_proof:gcp_proof(root)
    calls = []
    monkeypatch.setattr(gcp, "plan_apply", lambda stage, values, **k: {"service_url": {"value": "https://example.run.app"}, "runtime_configuration": {"value": {"paused": paused}}})
    monkeypatch.setattr(gcp, "verify_service_state", lambda *a: None)
    monkeypatch.setattr(gcp, "run", lambda command, **k: calls.append(command))
    gcp.change_pause_state(args, paused)
    report = json.loads((root / ".tools/gcp-deployment.json").read_text())
    assert report["tenant_auth_release"] == int(has_proof)
    assert report["paused"] is paused and report["image"] == GCP_IMAGE
    assert len(calls) == (0 if paused else 1)
    if calls:assert "smoke_cloud.py" in calls[0][1] and not any("credentials" in str(x) for x in calls[0])


@pytest.mark.parametrize("report", [{}, {"status": "passed", "image_id": LOCAL_IMAGE, "tenant_auth_release": True},
    {"status": "failed", "image_id": LOCAL_IMAGE, "tenant_auth_release": 1}, {"status": "passed", "image_id": "sha256:" + "d" * 64, "tenant_auth_release": 1}])
def test_gcp_missing_or_stale_local_proof_revalidates_exact_immutable_image_once(gcp_local, monkeypatch, report):
    root, args = gcp_local
    path = root / ".tools/gcp-local-validation.json";path.write_text(json.dumps(report))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:return json.dumps([{"Id": LOCAL_IMAGE, "Os": "linux", "Architecture": "amd64"}])
        assert command[command.index("--image") + 1] == LOCAL_IMAGE
        assert command[command.index("--emulator-image") + 1] == gcp.FIRESTORE_EMULATOR
        path.write_text(json.dumps({"status": "passed", "image_id": LOCAL_IMAGE, "tenant_auth_release": 1}))
        return ""
    monkeypatch.setattr(gcp, "run", run)
    assert gcp.validated_local_image(args.local_image) == LOCAL_IMAGE
    assert len(calls) == 2


def test_gcp_matching_local_proof_skips_duplicate_emulator_but_failed_validation_blocks_push(gcp_local, monkeypatch):
    root, args = gcp_local
    path = root / ".tools/gcp-local-validation.json"
    path.write_text(json.dumps({"status": "passed", "image_id": LOCAL_IMAGE, "tenant_auth_release": 1}))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return json.dumps([{"Id": LOCAL_IMAGE, "Os": "linux", "Architecture": "amd64"}]) if command[:3] == ["docker", "image", "inspect"] else ""
    monkeypatch.setattr(gcp, "run", run)
    assert gcp.validated_local_image(args.local_image) == LOCAL_IMAGE and len(calls) == 1
    path.unlink();calls.clear()
    monkeypatch.setattr(gcp, "cloud", lambda *a, **k: pytest.fail("No cloud registry login before exact auth validation"))
    with pytest.raises(RuntimeError, match="lacks a passed"):
        gcp.build_push(args, "asia-southeast1-docker.pkg.dev/" + PROJECT + "/ticketpilot-apartments")


@pytest.mark.parametrize("private_validation", [False, True])
def test_gcp_routine_deploy_uses_no_tenant_passwords_without_explicit_workflow_opt_in(gcp_local, monkeypatch, private_validation):
    root, args = gcp_local
    calls = []
    monkeypatch.setattr(gcp, "preflight", lambda a: "billing-not-used")
    monkeypatch.setattr(gcp, "database_mode", lambda a: False)
    monkeypatch.setattr(gcp, "upload_secrets", lambda a: None)
    monkeypatch.setattr(gcp, "build_push", lambda *a: GCP_IMAGE)
    monkeypatch.setattr(gcp, "plan_apply", lambda *a, **k: {"service_url": {"value": "https://example.run.app"}, "runtime_configuration": {"value": {"paused": False}}})
    monkeypatch.setattr(gcp, "cloud", lambda *a, **k: {})
    monkeypatch.setattr(gcp, "run", lambda command, **k: calls.append(command))
    command = ["--project", PROJECT, "--stage", "deploy"]
    private_file = root / ".secrets/current-private.json"
    if private_validation:command += ["--validate-tenant-workflow", "--credentials-file", str(private_file)]
    assert gcp.main(command) == 0
    full = [c for c in calls if "validate_gcp_deployment.py" in str(c)]
    assert len(full) == int(private_validation)
    assert any("smoke_cloud.py" in str(c) for c in calls)
    if full:assert full[0][-2:] == ["--credentials-file", str(private_file)]
    assert json.loads((root / ".tools/gcp-deployment.json").read_text())["tenant_auth_release"] == 1


def test_gcp_publication_uses_the_validated_id_and_keeps_docker_endpoint_and_token_private(gcp_local, monkeypatch):
    root, args = gcp_local
    (root / ".tools/gcp-local-validation.json").write_text(json.dumps({"status": "passed", "image_id": LOCAL_IMAGE, "tenant_auth_release": 1}))
    calls = []
    secret = "synthetic-oauth-token-not-a-real-credential"
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ["docker", "image", "inspect"]:return json.dumps([{"Id": LOCAL_IMAGE, "Os": "linux", "Architecture": "amd64"}])
        if command[:3] == ["docker", "context", "inspect"]:return "unix:///var/run/docker.sock"
        return ""
    def cloud(args, *command, **kwargs):
        if command == ("auth", "print-access-token"):return secret
        assert command[:4] == ("artifacts", "docker", "images", "describe")
        return {"image_summary": {"digest": "sha256:" + "d" * 64}}
    monkeypatch.setattr(gcp, "run", run);monkeypatch.setattr(gcp, "cloud", cloud)
    result = gcp.build_push(args, "asia-southeast1-docker.pkg.dev/" + PROJECT + "/ticketpilot-apartments")
    assert result.endswith("@sha256:" + "d" * 64)
    tag = next(command for command, _ in calls if command[:2] == ["docker", "tag"])
    assert tag[2] == LOCAL_IMAGE and args.local_image not in tag
    login, options = next((command, options) for command, options in calls if "login" in command)
    push = next(command for command, _ in calls if "push" in command)
    assert options["data"] == secret
    assert login[login.index("--host") + 1] == push[push.index("--host") + 1] == "unix:///var/run/docker.sock"
    assert all(secret not in " ".join(command) for command, _ in calls)
    assert not Path(login[login.index("--config") + 1]).exists()
