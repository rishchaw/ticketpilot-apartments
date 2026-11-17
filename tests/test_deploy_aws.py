"""Lifecycle safety checks using fictional plans and mocks; no AWS/Docker calls."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import deploy_aws as aws

ACCOUNT = "123456789012"
IMAGE = ACCOUNT + ".dkr.ecr.ap-southeast-1.amazonaws.com/ticketpilot-aws@sha256:" + "a" * 64


@pytest.fixture
def values():
    return {"region": aws.REGION, "image_uri": IMAGE, "paused": False, "reserved_concurrency": 1,
            "enable_bedrock": False, "protect_ticket_data": True, "manager_refresh_seconds": 0, "queue_limit": 20}


@pytest.fixture
def plan(values):
    resources = [
        {"address": "aws_lambda_function.app", "mode": "managed", "values": {
            "function_name": aws.FUNCTION, "image_uri": IMAGE, "reserved_concurrent_executions": 1,
            "memory_size": 1024, "timeout": 30, "architectures": ["x86_64"], "package_type": "Image",
            "vpc_config": [], "file_system_config": [], "environment": [{"variables": {
                "LLM_PROVIDER": "none", "STORAGE_MODE": "dynamodb", "APARTMENT_REFRESH_SECONDS": "0", "APARTMENT_QUEUE_LIMIT": "20"}}]}},
        {"address": "aws_dynamodb_table.tickets", "mode": "managed", "values": {
            "name": "ticketpilot-aws-tickets", "billing_mode": "PAY_PER_REQUEST", "deletion_protection_enabled": True}},
        {"address": "aws_cloudwatch_log_group.app", "mode": "managed", "values": {"retention_in_days": 7}},
    ]
    return {"complete": True, "planned_values": {"root_module": {"resources": resources}},
            "resource_changes": [{"address": resource["address"], "mode": "managed", "change": {
                "actions": ["create"], "before": None, "after": deepcopy(resource["values"]), "after_unknown": {}}} for resource in resources]}


def function(plan):
    return plan["planned_values"]["root_module"]["resources"][0]["values"]


def scaling_plan(plan):
    for change in plan["resource_changes"]:
        change["change"]["actions"] = ["no-op"]
    change = plan["resource_changes"][0]["change"]
    change["actions"] = ["update"]
    change["before"] = deepcopy(function(plan))
    function(plan)["reserved_concurrent_executions"] = 0
    change["after"] = deepcopy(function(plan))
    return plan


def test_new_app_plan_is_accepted_with_protected_on_demand_storage_and_no_ai(plan, values):
    assert len(aws.validate_plan(plan, "app", values, ACCOUNT)) == 3


@pytest.mark.parametrize("actions", [["delete"], ["delete", "create"], ["create", "delete"]])
def test_deletions_and_replacements_are_rejected(plan, values, actions):
    plan["resource_changes"][1]["change"]["actions"] = actions
    with pytest.raises(aws.DeploymentError, match="deletion or replacement"):
        aws.validate_plan(plan, "app", values, ACCOUNT)


def test_unexpected_paid_resource_is_rejected_even_inside_a_child_module(plan, values):
    plan["planned_values"]["root_module"]["child_modules"] = [{"resources": [{"address": "module.extra.aws_instance.host", "mode": "managed", "values": {}}]}]
    with pytest.raises(aws.DeploymentError, match="outside"):
        aws.validate_plan(plan, "app", values, ACCOUNT)


@pytest.mark.parametrize("key,value", [("LLM_PROVIDER", "bedrock"), ("ADMIN_TOKEN", "fictional-plaintext"), ("APARTMENT_REFRESH_SECONDS", "10")])
def test_paid_generation_plaintext_tokens_and_background_refresh_are_rejected(plan, values, key, value):
    function(plan)["environment"][0]["variables"][key] = value
    with pytest.raises(aws.DeploymentError):
        aws.validate_plan(plan, "app", values, ACCOUNT)


@pytest.mark.parametrize("key,value", [("billing_mode", "PROVISIONED"), ("deletion_protection_enabled", False), ("replica", [{"region_name": "us-east-1"}])])
def test_storage_cost_or_protection_changes_are_rejected(plan, values, key, value):
    plan["planned_values"]["root_module"]["resources"][1]["values"][key] = value
    with pytest.raises(aws.DeploymentError):
        aws.validate_plan(plan, "app", values, ACCOUNT)


def test_pause_permits_only_existing_function_concurrency_update(plan, values):
    scaling_plan(plan)
    values["paused"] = True
    assert aws.validate_plan(plan, "app", values, ACCOUNT, scaling_only=True) == [{"address": "aws_lambda_function.app", "actions": ["update"]}]


def test_pause_refuses_image_change_even_when_new_digest_is_valid(plan, values):
    scaling_plan(plan)
    values["paused"] = True
    changed = IMAGE[:-64] + "b" * 64
    values["image_uri"] = changed
    function(plan)["image_uri"] = changed
    plan["resource_changes"][0]["change"]["after"]["image_uri"] = changed
    with pytest.raises(aws.DeploymentError, match="cannot change"):
        aws.validate_plan(plan, "app", values, ACCOUNT, scaling_only=True)


def test_pause_refuses_new_function_or_other_resource_update(plan, values):
    values["paused"] = True
    function(plan)["reserved_concurrent_executions"] = 0
    with pytest.raises(aws.DeploymentError, match="existing Lambda"):
        aws.validate_plan(plan, "app", values, ACCOUNT, scaling_only=True)


@pytest.mark.parametrize("image", [IMAGE.replace(ACCOUNT, "999999999999"), IMAGE.replace("ap-southeast-1", "us-east-1"), IMAGE.split("@")[0] + ":latest"])
def test_cross_account_region_or_mutable_image_cannot_be_promoted(image):
    with pytest.raises(aws.DeploymentError, match="immutable"):
        aws.validate_image(image, ACCOUNT)


def test_auto_concurrency_respects_new_account_quota_and_existing_reservation():
    assert aws.choose_concurrency({"AccountLimit": {"UnreservedConcurrentExecutions": 10}}) == -1
    assert aws.choose_concurrency({"AccountLimit": {"UnreservedConcurrentExecutions": 101}}) == 1
    assert aws.choose_concurrency({"AccountLimit": {"UnreservedConcurrentExecutions": 100}}, current=1, requested="1") == 1
    with pytest.raises(aws.DeploymentError, match="without upgrading"):
        aws.choose_concurrency({"AccountLimit": {"UnreservedConcurrentExecutions": 10}}, requested="2")


def test_named_profiles_and_reviewed_variables_override_ambient_credentials_without_config_writes():
    original = {"AWS_ACCESS_KEY_ID": "fictional-key", "AWS_SECRET_ACCESS_KEY": "fictional-secret", "AWS_PROFILE": "wrong",
                "AWS_ENDPOINT_URL_LAMBDA": "http://elsewhere", "TF_VAR_enable_bedrock": "true", "TF_CLI_ARGS_plan": "-destroy",
                "AWS_CONFIG_FILE": "existing-config", "PATH": "existing-path"}
    result = aws.scoped_environment(original, "ticketpilot-terraform")
    assert result["AWS_PROFILE"] == "ticketpilot-terraform"
    assert result["AWS_CONFIG_FILE"] == "existing-config" and result["PATH"] == "existing-path"
    assert not set(original).intersection(result) - {"AWS_PROFILE", "AWS_CONFIG_FILE", "PATH"}
    assert original["AWS_PROFILE"] == "wrong"


def test_redeploy_preserves_saved_and_manual_pause_and_never_requests_secret_overwrite(monkeypatch, tmp_path, values):
    saved = {**values, "paused": True}
    aws.private_write(aws.settings_path(tmp_path, "app"), "".join(key + " = " + json.dumps(value) + "\n" for key, value in saved.items()))
    commands = SimpleNamespace(root=tmp_path, args=SimpleNamespace(reserved_concurrency=None), run=lambda command: command)
    monkeypatch.setattr(aws, "current_function", lambda _: {"Configuration": {}})
    monkeypatch.setattr(aws, "current_concurrency", lambda _: 0)
    monkeypatch.setattr(aws, "push_image", lambda *_: IMAGE)
    captured = {}
    def apply(commands, stage, candidate, account):
        captured.update(candidate)
        return {}
    monkeypatch.setattr(aws, "plan_apply", apply)
    monkeypatch.setattr(aws, "observe", lambda commands, account, expected: {"paused": expected["paused"]})
    calls = []
    commands.run = lambda command: calls.append(command)
    assert aws.deploy(commands, ACCOUNT, {"AccountLimit": {"UnreservedConcurrentExecutions": 101}})["paused"] is True
    assert captured["paused"] is True
    assert len(calls) == 1 and "upload_aws_secrets.py" in calls[0][1] and "--overwrite" not in calls[0]


def test_existing_function_without_private_settings_is_not_adopted(monkeypatch, tmp_path):
    commands = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(aws, "current_function", lambda _: {"Configuration": {}})
    monkeypatch.setattr(aws, "push_image", lambda *_: pytest.fail("No image push before ownership/settings review"))
    with pytest.raises(aws.DeploymentError, match="restore its private settings"):
        aws.deploy(commands, ACCOUNT, {})


def test_rejected_plan_does_not_apply_or_replace_saved_settings(tmp_path, values, plan):
    path = aws.settings_path(tmp_path, "app")
    aws.private_write(path, 'region = "ap-southeast-1"\n')
    original = path.read_bytes()
    plan["resource_changes"][0]["change"]["actions"] = ["delete"]
    calls = []
    def terraform(stage, *arguments):
        calls.append(arguments)
        return json.dumps(plan) if arguments[0] == "show" else ""
    commands = SimpleNamespace(root=tmp_path, terraform=terraform)
    with pytest.raises(aws.DeploymentError):
        aws.plan_apply(commands, "app", values, ACCOUNT)
    assert not any(call[0] == "apply" for call in calls)
    assert path.read_bytes() == original
    assert not (tmp_path / ".tools/aws/app-candidate.tfvars.json").exists()
    assert not (tmp_path / ".tools/aws/app.tfplan").exists()


def test_atomic_write_preserves_previous_record_if_replace_fails(monkeypatch, tmp_path):
    path = tmp_path / "record.json"
    aws.private_write(path, {"paused": True})
    original = path.read_bytes()
    def fail(*args):
        raise OSError("fictional disk interruption")
    monkeypatch.setattr(aws.os, "replace", fail)
    with pytest.raises(OSError):
        aws.private_write(path, {"paused": False})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_docker_promotion_binds_tested_image_id_and_never_persists_registry_password(tmp_path):
    image_id = "sha256:" + "c" * 64
    token = "fictional-short-lived-ecr-password"
    repository = IMAGE.split("@", 1)[0]
    class FakeCommands:
        root = tmp_path
        args = SimpleNamespace(skip_build=True, local_image="local:tested")
        def __init__(self):
            self.calls, self.validation = [], []
        def docker(self, *arguments, data=None, timeout=900):
            self.calls.append((arguments, data))
            if arguments[:2] == ("info", "--format"):
                return "linux"
            if arguments[:2] == ("image", "inspect"):
                return json.dumps([{"Id": image_id, "Architecture": "amd64", "Os": "linux"}])
            if arguments[:2] == ("context", "inspect"):
                return "npipe:////./pipe/dockerDesktopLinuxEngine"
            return ""
        def aws(self, *arguments, text=False):
            if arguments[:2] == ("ecr", "describe-repositories"):
                return {"repositories": [{"repositoryUri": repository, "imageTagMutability": "IMMUTABLE"}]}
            if arguments[:2] == ("ecr", "get-login-password"):
                return token
            if arguments[:2] == ("ecr", "describe-images"):
                return {"imageDetails": [{"imageDigest": "sha256:" + "a" * 64}]}
            pytest.fail("Unexpected cloud operation in fake client")
        def run(self, command, timeout=600):
            self.validation.append(command)
            return ""
    commands = FakeCommands()
    assert aws.push_image(commands, ACCOUNT) == IMAGE
    assert commands.validation[0][-2:] == ["--image", image_id]
    tag = next(arguments for arguments, _ in commands.calls if arguments[0] == "tag")
    assert tag[1] == image_id
    login = next((arguments, data) for arguments, data in commands.calls if "login" in arguments)
    assert login[1] == token + "\n" and token not in str(login[0])
    config_path = Path(login[0][1])
    assert not config_path.exists()
    assert "--host" in login[0]
    assert all(token not in str(arguments) for arguments, _ in commands.calls)


def test_optional_counted_monthly_budget_address_matches_terraform():
    resources = [{"address": "aws_ecr_repository.app", "mode": "managed", "values": {
        "name": "ticketpilot-aws", "image_tag_mutability": "IMMUTABLE"}},
        {"address": "aws_budgets_budget.monthly[0]", "mode": "managed", "values": {
            "budget_type": "COST", "limit_unit": "USD", "limit_amount": "10", "time_unit": "MONTHLY"}}]
    plan = {"complete": True, "planned_values": {"root_module": {"resources": resources}},
            "resource_changes": [{"address": value["address"], "mode": "managed", "change": {"actions": ["create"]}} for value in resources]}
    assert len(aws.validate_plan(plan, "bootstrap", {}, ACCOUNT)) == 2
    resources[1]["values"]["limit_amount"] = "50"
    with pytest.raises(aws.DeploymentError, match="USD10"):
        aws.validate_plan(plan, "bootstrap", {}, ACCOUNT)


@pytest.fixture
def observe_harness(monkeypatch, tmp_path, values):
    import httpx
    url = "https://abcdefghijklmnop.lambda-url.ap-southeast-1.on.aws"
    commands = SimpleNamespace(root=tmp_path, aws=lambda *arguments: {"FunctionUrl": url})
    monkeypatch.setattr(aws, "current_function", lambda _: {"Code": {"ResolvedImageUri": IMAGE},
        "Configuration": {"Environment": {"Variables": {"LLM_PROVIDER": "none", "STORAGE_MODE": "dynamodb"}}}})
    monkeypatch.setattr(aws, "current_concurrency", lambda _: 1)
    clock = {"value": 0.0}
    monkeypatch.setattr(aws.time, "monotonic", lambda: clock["value"])
    monkeypatch.setattr(aws.time, "sleep", lambda seconds: clock.update(value=clock["value"] + seconds))
    return commands, values, clock, url


def test_observe_retries_initial_connection_failure_then_verifies_health(monkeypatch, observe_harness):
    import httpx
    commands, expected, clock, url = observe_harness
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("fictional transient endpoint propagation", request=request)
        return httpx.Response(200, json={"storage_mode": "dynamodb"})
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    report = aws.observe(commands, ACCOUNT, expected=expected)
    assert report["health_verified"] is True and report["health_http_status"] == 200
    assert report["health_last_error_type"] is None
    assert len(calls) == 2 and 0 < clock["value"] < 90
    assert calls[0].extensions["timeout"]["read"] == 35


def test_observe_deadline_exhaustion_reports_only_safe_last_error_type(monkeypatch, observe_harness):
    import httpx
    commands, expected, clock, url = observe_harness
    calls = []
    sensitive_error = "fictional-sensitive-diagnostic-should-not-appear"
    def handler(request):
        calls.append(request)
        raise httpx.ConnectError(sensitive_error, request=request)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(aws.DeploymentError, match="ConnectError") as caught:
        aws.observe(commands, ACCOUNT, expected=expected)
    assert len(calls) > 1 and clock["value"] == 90
    assert sensitive_error not in str(caught.value) and url not in str(caught.value)
    assert "not rolled back" in str(caught.value)
    assert not (commands.root / ".tools/aws-service-state.json").exists()


def test_observe_paused_function_still_accepts_concurrency_zero_http429(monkeypatch, observe_harness):
    import httpx
    commands, expected, clock, _url = observe_harness
    expected["paused"] = True
    monkeypatch.setattr(aws, "current_concurrency", lambda _: 0)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(lambda request: httpx.Response(429)), **kwargs))
    report = aws.observe(commands, ACCOUNT, expected=expected)
    assert report["paused"] is True and report["health_verified"] is True
    assert report["health_http_status"] == 429 and clock["value"] == 0


@pytest.mark.parametrize("paused", [False, True])
def test_successful_apply_leaves_stop_eligible_pending_record_when_health_fails(monkeypatch, tmp_path, paused):
    url = "https://abcdefghijklmnop.lambda-url.ap-southeast-1.on.aws/"
    commands = SimpleNamespace(root=tmp_path, args=SimpleNamespace(reserved_concurrency=None), run=lambda *_: "")
    monkeypatch.setattr(aws, "read_settings", lambda *a, **k: {"paused": paused, "reserved_concurrency": -1})
    monkeypatch.setattr(aws, "current_function", lambda _: None)
    monkeypatch.setattr(aws, "push_image", lambda *_: IMAGE)
    applied = []
    def apply(commands, stage, values, account):
        applied.append(dict(values))
        return {"service_url": {"value": url, "sensitive": False}}
    monkeypatch.setattr(aws, "plan_apply", apply)
    def unreachable(*a, **k):
        raise aws.DeploymentError("fictional HTTP verification deadline")
    monkeypatch.setattr(aws, "observe", unreachable)
    with pytest.raises(aws.DeploymentError, match="verification deadline"):
        aws.deploy(commands, ACCOUNT, {"AccountLimit": {"UnreservedConcurrentExecutions": 10}})
    record = json.loads((tmp_path / ".tools/aws-deployment.json").read_text())
    # This is the exact eligibility field read by scripts/stop_services.py.
    assert record.get("deployed") is True and len(applied) == 1
    assert record["health_verified"] is False and record["verification_pending"] is True
    assert record["paused"] is paused and record["reserved_concurrency"] == (0 if paused else -1)
    assert record["image_uri"] == IMAGE and record["account_id"] == ACCOUNT
    assert record["function_name"] == "ticketpilot-aws" and record["region"] == "ap-southeast-1"
    assert record["url"] == url.rstrip("/") and record["data_retained"] is True


def test_failed_apply_does_not_invent_a_deployed_record(monkeypatch, tmp_path):
    commands = SimpleNamespace(root=tmp_path, args=SimpleNamespace(reserved_concurrency=None), run=lambda *_: "")
    monkeypatch.setattr(aws, "current_function", lambda _: None)
    monkeypatch.setattr(aws, "push_image", lambda *_: IMAGE)
    def rejected(*a, **k):
        raise aws.DeploymentError("fictional apply rejection")
    monkeypatch.setattr(aws, "plan_apply", rejected)
    monkeypatch.setattr(aws, "observe", lambda *a, **k: pytest.fail("Health must not run after apply rejection"))
    with pytest.raises(aws.DeploymentError, match="apply rejection"):
        aws.deploy(commands, ACCOUNT, {"AccountLimit": {"UnreservedConcurrentExecutions": 10}})
    assert not (tmp_path / ".tools/aws-deployment.json").exists()


def test_pending_record_omits_an_untrusted_output_url_but_preserves_stop_eligibility(tmp_path, values):
    commands = SimpleNamespace(root=tmp_path)
    record = aws.record_applied(commands, ACCOUNT, values, {"service_url": {"value": "https://example.invalid/", "sensitive": False}})
    assert record["deployed"] is True and record["verification_pending"] is True
    assert "url" not in record and record["health_verified"] is False
