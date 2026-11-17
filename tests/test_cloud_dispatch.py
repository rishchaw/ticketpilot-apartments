"""Offline dispatch/attestation tests; all remote and Docker actions are mocked."""
import json
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from scripts import cloud

GCP_URL = "https://ticketpilot-apartments-example-as.a.run.app"
GCP_SECOND = "https://ticketpilot-apartments-123456789.asia-southeast1.run.app"
AWS_URL = "https://abcdefghijklmnop.lambda-url.ap-southeast-1.on.aws"
ACCOUNT = "123456789012"


def args(provider="aws", action="deploy", *extra):
    return cloud.parser().parse_args([provider, action, *extra])


def save(root, provider, paused=True, **extra):
    record = {"paused": paused, "region": cloud.REGIONS[provider],
              "url": AWS_URL if provider == "aws" else GCP_URL,
              **({"account_id": ACCOUNT} if provider == "aws" else {"project": "project-demo-123"}), **extra}
    cloud.aws_native.private_write(root / ".tools" / (provider + "-deployment.json"), record)
    return record


class FakeRunner:
    def __init__(self, root):
        self.root, self.calls = root, []
    def gcp(self, context):
        raise cloud.ControlUnavailable("fictional expired login")
    def native(self, provider, stage, options):
        self.calls.append((provider, stage))
        return "{}"
    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return ""


def mock_http(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def paused_gcp_service(*, tags=False, paused=True):
    return {"metadata": {"name": cloud.GCP_SERVICE, "annotations": {
        "run.googleapis.com/scalingMode": "manual" if paused else "automatic",
        "run.googleapis.com/manualInstanceCount": "0",
        "run.googleapis.com/urls": json.dumps([GCP_URL, GCP_SECOND])}},
        "status": {"url": GCP_URL, "traffic": [{"tag": "preview"}] if tags else []}}


def test_no_record_makes_only_a_local_scope_statement_without_cloud_queries(tmp_path):
    runner = FakeRunner(tmp_path)
    proof = cloud.guard_other_provider(runner, args())
    assert proof["evidence"] == "no_local_deployment_record" and not runner.calls


def test_expired_other_login_requires_explicit_attestation_before_any_deployment(tmp_path):
    save(tmp_path, "gcp")
    runner = FakeRunner(tmp_path)
    with pytest.raises(cloud.CloudError, match="Cannot authenticate"):
        cloud.execute(runner, args())
    assert runner.calls == []


def test_attestation_requires_recorded_pause_and_fresh_unavailable_urls(monkeypatch, tmp_path):
    save(tmp_path, "gcp", verified_urls=[{"url": GCP_SECOND, "health_http_status": 503}])
    requested = []
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(503)
    mock_http(monkeypatch, handler)
    proof = cloud.guard_other_provider(FakeRunner(tmp_path), args("aws", "deploy", "--confirm-other-offline"))
    assert proof["evidence"] == "operator_attestation_and_fresh_public_http"
    assert proof["authenticated_cloud_read"] is False
    assert proof["paused"] is True and len(proof["verified_urls"]) == 2
    assert {value.rsplit("/health", 1)[0] for value in requested} == {GCP_URL, GCP_SECOND}
    assert "not an authenticated" in proof["note"]


@pytest.mark.parametrize("recorded", [False, None])
def test_attestation_cannot_override_an_active_or_unknown_record(tmp_path, recorded):
    save(tmp_path, "gcp", paused=recorded)
    with pytest.raises(cloud.CloudError, match="recorded paused"):
        cloud.guard_other_provider(FakeRunner(tmp_path), args("aws", "resume", "--confirm-other-offline"))


@pytest.mark.parametrize("status", [200, 301, 401, 403, 429, 500])
def test_attestation_refuses_an_available_redirected_or_unexpected_url(monkeypatch, tmp_path, status):
    save(tmp_path, "gcp")
    mock_http(monkeypatch, lambda request: httpx.Response(status))
    with pytest.raises(cloud.CloudError, match="expected paused"):
        cloud.guard_other_provider(FakeRunner(tmp_path), args("aws", "deploy", "--confirm-other-offline"))


def test_dns_failure_is_not_offline_proof(monkeypatch, tmp_path):
    save(tmp_path, "gcp")
    def handler(request):
        raise httpx.ConnectError("fictional DNS failure", request=request)
    mock_http(monkeypatch, handler)
    with pytest.raises(cloud.CloudError, match="not proof"):
        cloud.guard_other_provider(FakeRunner(tmp_path), args("aws", "deploy", "--confirm-other-offline"))


@pytest.mark.parametrize("tags,paused", [(True, True), (False, False)])
def test_live_authenticated_active_state_cannot_be_overridden_by_attestation(monkeypatch, tmp_path, tags, paused):
    save(tmp_path, "gcp")
    runner = FakeRunner(tmp_path)
    runner.gcp = lambda context: paused_gcp_service(tags=tags, paused=paused)
    with pytest.raises(cloud.CloudError, match="other provider is active"):
        cloud.guard_other_provider(runner, args("aws", "deploy", "--confirm-other-offline"))


def test_authenticated_gcp_pause_verifies_all_known_urls(monkeypatch, tmp_path):
    save(tmp_path, "gcp")
    runner = FakeRunner(tmp_path)
    runner.gcp = lambda context: paused_gcp_service()
    mock_http(monkeypatch, lambda request: httpx.Response(503))
    proof = cloud.guard_other_provider(runner, args())
    assert proof["authenticated_cloud_read"] is True and len(proof["verified_urls"]) == 2
    assert proof["evidence"] == "authenticated_cloud_read_and_fresh_public_http"


def test_authenticated_aws_guard_requires_zero_concurrency_and_matching_account(monkeypatch, tmp_path):
    save(tmp_path, "aws")
    runner = FakeRunner(tmp_path)
    def response(options, *command):
        return ({"Account": ACCOUNT} if command[0] == "sts" else
                {"ReservedConcurrentExecutions": 0} if command[1] == "get-function-concurrency" else
                {"FunctionUrl": AWS_URL})
    runner.aws = response
    mock_http(monkeypatch, lambda request: httpx.Response(429))
    proof = cloud.guard_other_provider(runner, args("gcp", "deploy"))
    assert proof["paused"] is True and proof["reserved_concurrency"] == 0
    runner.aws = lambda *arguments: {"Account": "999999999999"}
    with pytest.raises(cloud.CloudError, match="recorded AWS account"):
        cloud.guard_other_provider(runner, args("gcp", "deploy", "--confirm-other-offline"))


def test_pause_attempts_cloud_even_if_local_monitoring_stop_fails(monkeypatch, tmp_path):
    runner = FakeRunner(tmp_path)
    def fail(_):
        raise cloud.CloudError("fictional Docker permissions")
    monkeypatch.setattr(cloud, "monitor_stop", fail)
    with pytest.raises(cloud.CloudError, match="Cloud pause completed"):
        cloud.execute(runner, args("aws", "pause"))
    assert runner.calls == [("aws", "pause")]


def test_aws_deploy_dispatches_bootstrap_then_deploy_and_apartment_acceptance(monkeypatch, tmp_path):
    runner = FakeRunner(tmp_path)
    order = []
    monkeypatch.setattr(cloud, "guard_other_provider", lambda *_: order.append("guard") or {"paused": True})
    monkeypatch.setattr(cloud, "monitor_stop", lambda *_: order.append("stop-monitoring") or {"stopped": True})
    monkeypatch.setattr(cloud, "aws_acceptance", lambda *_: order.append("acceptance") or {"status": "passed"})
    runner.native = lambda provider, stage, options: order.append(stage)
    report = cloud.execute(runner, args())
    assert order == ["guard", "stop-monitoring", "bootstrap", "deploy", "acceptance"]
    assert report["acceptance"]["status"] == "passed"


def test_gcp_deploy_dispatches_native_all_and_does_not_invoke_aws(monkeypatch, tmp_path):
    save(tmp_path, "gcp")
    runner = FakeRunner(tmp_path)
    monkeypatch.setattr(cloud, "guard_other_provider", lambda *_: {"evidence": "no_local_deployment_record"})
    monkeypatch.setattr(cloud, "monitor_stop", lambda *_: {"stopped": True})
    monkeypatch.setattr(cloud, "build_validate_gcp", lambda *_: {"status": "passed"})
    cloud.execute(runner, args("gcp", "deploy"))
    assert runner.calls == [("gcp", "all")]


def test_gcp_status_reads_control_plane_without_pausing_or_resuming(monkeypatch, tmp_path):
    save(tmp_path, "gcp")
    runner = FakeRunner(tmp_path)
    runner.gcp = lambda context: paused_gcp_service()
    mock_http(monkeypatch, lambda request: httpx.Response(503))
    report = cloud.execute(runner, args("gcp", "status"))
    assert report["paused"] is True and report["authenticated_cloud_read"] is True
    assert runner.calls == []


def test_monitor_start_uses_only_local_services_and_300_second_secret_file_scrape(monkeypatch, tmp_path):
    save(tmp_path, "aws", paused=False)
    token = "fictional-metrics-token-" + "x" * 32
    env_text = "ADMIN_TOKEN=" + "a" * 32 + "\nMETRICS_TOKEN=" + token + "\nGRAFANA_ADMIN_PASSWORD=" + "g" * 32 + "\n"
    (tmp_path / ".env").write_text(env_text)
    runner = FakeRunner(tmp_path)
    monkeypatch.setattr(cloud, "authenticated_state", lambda *a: {"paused": False, "known_urls": {AWS_URL}})
    monkeypatch.setattr(cloud, "monitor_stop", lambda _: {"stopped": True})
    monkeypatch.setattr(cloud.shutil, "which", lambda name: "docker")
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, text="ticketpilot_requests_total 1\n")
    mock_http(monkeypatch, handler)
    report = cloud.monitor_start(runner, args("aws", "monitor-start"))
    config_text = (tmp_path / "monitoring/prometheus/cloud.yml").read_text()
    config = json.loads(config_text)
    assert config["global"]["scrape_interval"] == "300s"
    assert config["scrape_configs"][0]["authorization"]["credentials_file"] == "/run/secrets/metrics-token"
    assert token not in config_text
    assert (tmp_path / ".secrets/metrics-token").read_text() == token
    assert (tmp_path / ".env").read_text() == env_text
    command, options = runner.calls[-1]
    assert command[-2:] == ["prometheus", "grafana"]
    assert "--no-deps" in command and "--force-recreate" in command and "app" not in command
    assert options["env"]["PROMETHEUS_CONFIG"].endswith("cloud.yml")
    assert requests[0].headers["Authorization"] == "Bearer " + token
    assert report["location"] == "local Docker only"


def test_paused_service_cannot_be_started_by_monitoring(monkeypatch, tmp_path):
    save(tmp_path, "aws", paused=True)
    runner = FakeRunner(tmp_path)
    with pytest.raises(cloud.CloudError, match="resume explicitly"):
        cloud.monitor_start(runner, args("aws", "monitor-start"))
    assert runner.calls == []


def test_unknown_docker_error_is_not_treated_as_a_stopped_engine():
    assert cloud.docker_offline("Cannot connect to the Docker daemon")
    assert not cloud.docker_offline("Access is denied")


def test_dispatch_lock_is_separate_from_native_aws_lock(tmp_path):
    with cloud.dispatch_lock(tmp_path):
        assert (tmp_path / ".tools/cloud-dispatch.lock").is_file()
        assert not (tmp_path / ".tools/aws/operation.lock").exists()
        with pytest.raises(cloud.CloudError, match="Another cloud action"):
            with cloud.dispatch_lock(tmp_path):
                pytest.fail("A concurrent provider switch acquired the same lock")
    assert not (tmp_path / ".tools/cloud-dispatch.lock").exists()


def test_authenticated_other_service_cannot_vouch_for_a_different_recorded_url(tmp_path):
    save(tmp_path, "gcp", url="https://different-service-as.a.run.app")
    runner = FakeRunner(tmp_path)
    runner.gcp = lambda context: paused_gcp_service()
    with pytest.raises(cloud.CloudError, match="do not match"):
        cloud.guard_other_provider(runner, args("aws", "deploy", "--confirm-other-offline"))


def test_aws_authenticated_url_must_match_record_even_if_account_id_was_not_recorded(tmp_path):
    save(tmp_path, "aws")
    runner = FakeRunner(tmp_path)
    def response(options, *command):
        return ({"Account": ACCOUNT} if command[0] == "sts" else
                {"ReservedConcurrentExecutions": 0} if command[1] == "get-function-concurrency" else
                {"FunctionUrl": AWS_URL.replace("abcdefghijklmnop", "differentfunction")})
    runner.aws = response
    with pytest.raises(cloud.CloudError, match="does not match"):
        cloud.guard_other_provider(runner, args("gcp", "deploy", "--confirm-other-offline"))


def test_failed_native_command_keeps_private_diagnostics_instead_of_losing_error(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="safe native stage\n", stderr="fictional provider validation error\n"))
    with pytest.raises(cloud.CloudError, match="cloud-last-command-error.log"):
        cloud.Runner(tmp_path).run(["python", "native.py"])
    assert "fictional provider validation error" in (tmp_path / ".tools/cloud-last-command-error.log").read_text()


def test_gcp_default_build_validates_and_promotes_exact_image_id(monkeypatch, tmp_path):
    runner = FakeRunner(tmp_path)
    image_id = "sha256:" + "d" * 64
    monkeypatch.setattr(cloud.shutil, "which", lambda _: "docker")
    calls = []
    def run(command, **options):
        calls.append(command)
        return image_id if command[1:3] == ["image", "inspect"] else ""
    runner.run = run
    options = args("gcp", "deploy", "--project", "project-demo-123")
    result = cloud.build_validate_gcp(runner, options)
    build = calls[0]
    assert build[:3] == ["docker", "buildx", "build"]
    assert build[build.index("--platform") + 1] == "linux/amd64"
    assert "--provenance=false" in build and "--load" in build
    assert build[build.index("-f") + 1] == "Dockerfile.gcp"
    assert calls[2] == ["docker", "pull", cloud.FIRESTORE_EMULATOR]
    validator = calls[3]
    assert validator[1].endswith("validate_firestore_local.py")
    assert validator[validator.index("--image") + 1] == image_id
    assert validator[validator.index("--emulator-image") + 1] == cloud.FIRESTORE_EMULATOR
    assert options.local_image == image_id and result["status"] == "passed"
    native = cloud.native_command(tmp_path, "gcp", "all", options)
    assert native[native.index("--local-image") + 1] == image_id


def test_gcp_skip_build_does_not_run_docker_or_emulator(monkeypatch, tmp_path):
    save(tmp_path, "gcp")
    runner = FakeRunner(tmp_path)
    monkeypatch.setattr(cloud, "guard_other_provider", lambda *_: {"evidence": "no_local_deployment_record"})
    monkeypatch.setattr(cloud, "monitor_stop", lambda *_: {"stopped": True})
    monkeypatch.setattr(cloud, "build_validate_gcp", lambda *_: pytest.fail("Explicit prevalidated-image path must skip local build/emulator"))
    report = cloud.execute(runner, args("gcp", "deploy", "--skip-build", "--local-image", "existing:tested"))
    assert runner.calls == [("gcp", "all")]
    assert "--skip-build" in report["acceptance"]["local_validation"]


def test_empty_unreserved_aws_cli_output_is_valid_authenticated_concurrency_minus_one(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud.shutil, "which", lambda _: "aws")
    def run(command, **options):
        if "get-caller-identity" in command:
            output = json.dumps({"Account": ACCOUNT})
        elif "get-function-concurrency" in command:
            output = " \n"  # AWS CLI emits no JSON object for an unreserved function.
        elif "get-function-url-config" in command:
            output = json.dumps({"FunctionUrl": AWS_URL})
        else:
            pytest.fail("Unexpected offline AWS command")
        return SimpleNamespace(returncode=0, stdout=output, stderr="")
    monkeypatch.setattr(cloud.subprocess, "run", run)
    runner = cloud.Runner(tmp_path)
    assert runner.aws(args(), "lambda", "get-function-concurrency", "--function-name", "ticketpilot-aws") == {}
    state = cloud.authenticated_state(runner, "aws", {"url": AWS_URL, "account_id": ACCOUNT}, args("gcp", "status"))
    assert state["reserved_concurrency"] == -1 and state["paused"] is False
    assert state["authenticated_cloud_read"] is True


@pytest.mark.parametrize("returncode,output,error", [(1, "", "AccessDeniedException"), (0, "malformed-json", "")])
def test_empty_output_fix_does_not_mask_failed_or_malformed_aws_cli_calls(monkeypatch, tmp_path, returncode, output, error):
    monkeypatch.setattr(cloud.shutil, "which", lambda _: "aws")
    monkeypatch.setattr(cloud.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=returncode, stdout=output, stderr=error))
    with pytest.raises(cloud.ControlUnavailable):
        cloud.Runner(tmp_path).aws(args(), "lambda", "get-function-concurrency", "--function-name", "ticketpilot-aws")
