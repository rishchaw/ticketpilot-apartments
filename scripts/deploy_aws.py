"""Explicit AWS lifecycle using existing profiles, Terraform state and immutable images.

This helper never signs in, writes AWS configuration, upgrades a plan, destroys
resources or enables hosted AI. The provider selector must keep GCP paused before
starting AWS. Status/preflight are read-only. See docs/AWS_DEPLOYMENT.md.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REGION = "ap-southeast-1"
FUNCTION = "ticketpilot-aws"
REPOSITORY = "ticketpilot-aws"
PARAMETERS = ("/ticketpilot-aws/admin-token", "/ticketpilot-aws/metrics-token")
ALLOWED = {
    "bootstrap": {"aws_ecr_repository.app", "aws_ecr_lifecycle_policy.app", "aws_budgets_budget.monthly[0]"},
    "app": {"aws_dynamodb_table.tickets", "aws_cloudwatch_log_group.app", "aws_iam_role.runtime",
            "aws_iam_role_policy.runtime", "aws_lambda_function.app", "aws_lambda_function_url.app",
            "aws_lambda_permission.url", "aws_lambda_permission.invoke"},
}
COMPUTED_LAMBDA = {"last_modified", "qualified_arn", "qualified_invoke_arn", "version", "signing_job_arn",
                   "signing_profile_version_arn", "invoke_arn", "arn", "id", "code_sha256"}


class DeploymentError(Exception):
    pass


class CommandError(DeploymentError):
    def __init__(self, label, result):
        match = re.search(r"An error occurred \(([A-Za-z0-9_.-]+)\)", result.stderr or "")
        self.code = match.group(1) if match else None
        super().__init__(label + " failed (exit " + str(result.returncode) +
                         (", " + self.code if self.code else "") + "); no credential output was printed")


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise DeploymentError("Refusing a symlink at an AWS generated-file path")
    data = value if isinstance(value, str) else json.dumps(value, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix="aws-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def operation_lock(root):
    path = root / ".tools/aws/operation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise DeploymentError("Another AWS operation holds operation.lock; inspect a stale lock before removing it") from error
    marker = uuid4().hex
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(marker)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        yield
    finally:
        if path.is_file() and path.read_text(encoding="utf-8") == marker:
            path.unlink()


def scoped_environment(source, profile):
    # Ambient keys, endpoint redirects and Terraform CLI/variable overrides must
    # not silently change the selected identity, destination or reviewed plan.
    blocked = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN",
               "AWS_DEFAULT_PROFILE", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
               "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "AWS_CONTAINER_CREDENTIALS_FULL_URI"}
    env = {key: value for key, value in source.items() if key not in blocked and
           not key.startswith(("TF_VAR_", "TF_CLI_ARGS", "AWS_ENDPOINT_URL"))}
    env.update(AWS_PROFILE=profile, AWS_REGION=REGION, AWS_DEFAULT_REGION=REGION,
               AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off", AWS_EC2_METADATA_DISABLED="true",
               AWS_SDK_LOAD_CONFIG="1", TF_IN_AUTOMATION="1", TF_INPUT="0")
    return env


def tool(name, root):
    candidate = shutil.which(name)
    if not candidate:
        local = root / ".tools" / (name + (".exe" if os.name == "nt" else ""))
        candidate = str(local) if local.is_file() else None
    if not candidate:
        raise DeploymentError("Install " + name + " first; this helper does not install tools")
    return candidate


class Commands:
    def __init__(self, args, root=ROOT):
        self.args, self.root = args, root
        self.aws_executable = tool("aws", root)
        self.terraform_profile = args.terraform_profile

    def run(self, command, *, cwd=None, data=None, profile=None, timeout=600):
        result = subprocess.run(list(map(str, command)), cwd=cwd or self.root,
            env=scoped_environment(os.environ, profile or self.args.profile), input=data,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise CommandError(Path(str(command[0])).name, result)
        return result.stdout

    def aws(self, *arguments, profile=None, text=False):
        result = self.run([self.aws_executable, *arguments, "--profile", profile or self.args.profile,
                           "--region", REGION, "--no-cli-pager", "--output", "text" if text else "json"],
                          profile=profile)
        return result.strip() if text else json.loads(result or "{}")

    def choose_terraform_profile(self):
        if not self.terraform_profile:
            configured = self.run([self.aws_executable, "configure", "list-profiles"]).splitlines()
            bridge = self.args.profile + "-terraform"
            self.terraform_profile = bridge if bridge in configured else self.args.profile
        return self.terraform_profile

    def terraform(self, stage, *arguments):
        return self.run([tool("terraform", self.root), *arguments],
                        cwd=self.root / "infra" / ("bootstrap" if stage == "bootstrap" else "aws"),
                        profile=self.choose_terraform_profile(), timeout=1200)

    def docker(self, *arguments, data=None, timeout=900):
        return self.run([tool("docker", self.root), *arguments], data=data, timeout=timeout)


def validate_account(account):
    if not isinstance(account, str) or not re.fullmatch(r"[0-9]{12}", account):
        raise DeploymentError("AWS returned an invalid account ID")
    return account


def validate_image(image, account):
    expected = re.escape(account + ".dkr.ecr." + REGION + ".amazonaws.com/" + REPOSITORY)
    if not isinstance(image, str) or not re.fullmatch(expected + r"@sha256:[0-9a-f]{64}", image):
        raise DeploymentError("Use the immutable TicketPilot ECR digest in the selected account and Singapore")
    return image


def choose_concurrency(settings, current=-1, requested="auto"):
    if requested == "-1":
        return -1
    limits = settings.get("AccountLimit", {})
    remaining = limits.get("UnreservedConcurrentExecutions")
    if not isinstance(remaining, int):
        raise DeploymentError("Lambda did not return a usable regional concurrency quota")
    desired = 1 if requested == "auto" else int(requested)
    if desired not in (1, 2):
        raise DeploymentError("Use auto, -1, 1 or 2 for active concurrency")
    # An existing reservation belongs to this function and can be reused.
    available = remaining + max(current, 0) - 100
    if available >= desired:
        return desired
    if requested == "auto":
        return -1
    raise DeploymentError("The regional quota cannot reserve the requested concurrency; use -1 or auto without upgrading")


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(unknown(item) for item in value)
    return value is True


def planned_resources(plan):
    def walk(module):
        yield from module.get("resources", [])
        for child in module.get("child_modules", []):
            yield from walk(child)
    return list(walk(plan.get("planned_values", {}).get("root_module", {})))


def validate_plan(plan, stage, values, account, *, scaling_only=False):
    if stage not in ALLOWED or plan.get("errored") or plan.get("complete") is False:
        raise DeploymentError("Terraform did not produce a complete successful known-stage plan")
    changes = []
    for resource in plan.get("resource_changes", []):
        change = resource.get("change", {})
        actions = change.get("actions")
        if resource.get("mode") == "data" and actions in (["read"], ["no-op"]):
            continue
        if resource.get("address") not in ALLOWED[stage] or actions not in (["no-op"], ["create"], ["update"]):
            raise DeploymentError("Plan includes an unexpected resource, deletion or replacement: " + str(resource.get("address")))
        if actions == ["no-op"]:
            continue
        if scaling_only:
            if resource.get("address") != "aws_lambda_function.app" or actions != ["update"]:
                raise DeploymentError("Pause/resume may only update the existing Lambda concurrency")
            before, after = change.get("before") or {}, change.get("after") or {}
            computed = change.get("after_unknown") or {}
            differences = {key for key in set(before) | set(after) if before.get(key) != after.get(key)
                           and not (key in COMPUTED_LAMBDA and unknown(computed.get(key)))}
            if differences - {"reserved_concurrent_executions"}:
                raise DeploymentError("Pause/resume cannot change the image, role, environment or other Lambda configuration")
            if any(unknown(value) for key, value in computed.items() if key not in COMPUTED_LAMBDA):
                raise DeploymentError("Pause/resume configuration must be known")
        changes.append({"address": resource["address"], "actions": actions})
    resources = {resource["address"]: resource.get("values", {}) for resource in planned_resources(plan)
                 if resource.get("mode") != "data"}
    if set(resources) - ALLOWED[stage]:
        raise DeploymentError("Planned resources include infrastructure outside this AWS deployment")
    if stage == "app":
        function = resources.get("aws_lambda_function.app")
        table = resources.get("aws_dynamodb_table.tickets")
        if not function or not table:
            raise DeploymentError("The complete app plan must include Lambda and the existing durable table")
        validate_image(values["image_uri"], account)
        if function.get("image_uri") != values["image_uri"] or function.get("function_name") != FUNCTION:
            raise DeploymentError("Lambda image/name differs from the selected deployment")
        expected = 0 if values.get("paused") else values["reserved_concurrency"]
        if function.get("reserved_concurrent_executions") != expected or expected not in (-1, 0, 1, 2):
            raise DeploymentError("Lambda concurrency differs from the requested low-cost pause state")
        if function.get("memory_size", 99999) > 1024 or function.get("timeout", 99999) > 30:
            raise DeploymentError("Lambda memory/timeout exceed the reviewed limits")
        if function.get("architectures") != ["x86_64"] or function.get("package_type") != "Image":
            raise DeploymentError("The deployment must remain the tested x86_64 Lambda container")
        if function.get("vpc_config") or function.get("file_system_config"):
            raise DeploymentError("This demo does not provision VPC or network-file-system infrastructure")
        environment = function.get("environment", [])
        runtime = environment[0].get("variables", {}) if len(environment) == 1 else {}
        if runtime.get("LLM_PROVIDER") != "none" or runtime.get("STORAGE_MODE") != "dynamodb":
            raise DeploymentError("Paid generation must stay disabled and durable DynamoDB enabled")
        if runtime.get("APARTMENT_REFRESH_SECONDS") != "0" or runtime.get("APARTMENT_QUEUE_LIMIT") != "20":
            raise DeploymentError("Manager refresh/queue differ from the reviewed low-traffic defaults")
        if runtime.get("ADMIN_TOKEN") or runtime.get("METRICS_TOKEN"):
            raise DeploymentError("Runtime access codes must use SSM references, never Terraform values")
        if table.get("name") != FUNCTION + "-tickets" or table.get("billing_mode") != "PAY_PER_REQUEST" or table.get("deletion_protection_enabled") is not True:
            raise DeploymentError("The protected durable table must use on-demand billing")
        if table.get("replica") or table.get("stream_enabled"):
            raise DeploymentError("This demo does not enable DynamoDB replicas or streams")
        logs = resources.get("aws_cloudwatch_log_group.app", {})
        if not 1 <= logs.get("retention_in_days", 99999) <= 7:
            raise DeploymentError("CloudWatch retention must stay within seven days")
    elif resources:
        repository = resources.get("aws_ecr_repository.app", {})
        if repository.get("name") != REPOSITORY or repository.get("image_tag_mutability") != "IMMUTABLE":
            raise DeploymentError("ECR must preserve the immutable TicketPilot repository")
        budget = resources.get("aws_budgets_budget.monthly[0]")
        if budget and (budget.get("budget_type") != "COST" or budget.get("limit_unit") != "USD" or
                       float(budget.get("limit_amount", "99999")) > 10 or budget.get("time_unit") != "MONTHLY"):
            raise DeploymentError("The optional budget must remain a monthly cost alert of at most USD10")
    return changes


def settings_path(root, stage):
    return root / "infra" / ("bootstrap" if stage == "bootstrap" else "aws") / "terraform.tfvars"


def read_settings(root, stage, *, required=False):
    path = settings_path(root, stage)
    if path.is_symlink():
        raise DeploymentError("Refusing symlinked AWS settings")
    if not path.exists():
        if required:
            raise DeploymentError("Restore this deployment's existing private Terraform settings before pause/resume")
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[a-z_]+", key.strip()):
            raise DeploymentError("Generated AWS settings use an unexpected format; review rather than overwrite them")
        try:
            values[key.strip()] = json.loads(value.strip())
        except json.JSONDecodeError as error:
            raise DeploymentError("Existing AWS settings need explicit review before rewriting") from error
    if values.get("region", REGION) != REGION or values.get("enable_bedrock", False) is not False:
        raise DeploymentError("Existing AWS settings select another region or enable paid generation")
    if values.get("protect_ticket_data", True) is not True:
        raise DeploymentError("Durable ticket data must remain protected")
    return values


def plan_apply(commands, stage, values, account, *, scaling_only=False):
    folder = commands.root / ".tools/aws"
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / (stage + "-candidate.tfvars.json")
    plan_path = folder / (stage + ".tfplan")
    private_write(candidate, values)
    try:
        commands.terraform(stage, "init", "-input=false", "-lockfile=readonly")
        commands.terraform(stage, "plan", "-input=false", "-lock-timeout=60s", "-out=" + str(plan_path), "-var-file=" + str(candidate))
        plan = json.loads(commands.terraform(stage, "show", "-json", str(plan_path)))
        changes = validate_plan(plan, stage, values, account, scaling_only=scaling_only)
        private_write(folder / (stage + "-plan-summary.json"), {"stage": stage, "changes": changes})
        print(json.dumps({"reviewed_plan": stage, "changes": changes}))
        commands.terraform(stage, "apply", "-input=false", "-lock-timeout=60s", str(plan_path))
        private_write(settings_path(commands.root, stage), "".join(key + " = " + json.dumps(value) + "\n" for key, value in sorted(values.items())))
        return json.loads(commands.terraform(stage, "output", "-json"))
    finally:
        # Plans and any partial plans can include sensitive provider information.
        candidate.unlink(missing_ok=True)
        plan_path.unlink(missing_ok=True)


def identify(commands):
    account = validate_account(commands.aws("sts", "get-caller-identity")["Account"])
    record = commands.root / ".tools/aws-account.json"
    expected = commands.args.account_id
    if record.exists():
        saved = json.loads(record.read_text(encoding="utf-8"))
        if saved.get("region") != REGION or saved.get("account_id") != account:
            raise DeploymentError("The selected AWS account/region differs from the recorded deployment")
    if expected and account != expected:
        raise DeploymentError("The selected profile authenticated to a different AWS account")
    return account


def preflight(commands, account, *, terraform=False):
    commands.run([sys.executable, "scripts/preflight_aws.py", "--profile", commands.args.profile, "--region", REGION])
    quota = commands.aws("lambda", "get-account-settings")
    if terraform:
        profile = commands.choose_terraform_profile()
        bridge = commands.aws("sts", "get-caller-identity", profile=profile)
        if bridge.get("Account") != account:
            raise DeploymentError("AWS CLI and Terraform profiles select different accounts")
    return quota


def current_function(commands):
    try:
        return commands.aws("lambda", "get-function", "--function-name", FUNCTION)
    except CommandError as error:
        if error.code == "ResourceNotFoundException":
            return None
        raise


def current_concurrency(commands):
    return commands.aws("lambda", "get-function-concurrency", "--function-name", FUNCTION).get("ReservedConcurrentExecutions", -1)


def push_image(commands, account):
    args = commands.args
    if commands.docker("info", "--format", "{{.OSType}}").strip() != "linux":
        raise DeploymentError("The Lambda image requires Docker's Linux container engine")
    if not args.skip_build:
        commands.docker("buildx", "build", "--platform", "linux/amd64", "--provenance=false", "--load",
                        "-f", "Dockerfile.lambda", "-t", args.local_image, ".", timeout=1200)
    inspected = json.loads(commands.docker("image", "inspect", args.local_image))[0]
    image_id = inspected.get("Id", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) or inspected.get("Architecture") != "amd64" or inspected.get("Os") != "linux":
        raise DeploymentError("Use the tested Linux amd64 Lambda image")
    # Bind validation and promotion to the same local image ID, even if its tag moves.
    commands.run([sys.executable, "scripts/validate_lambda_image.py", "--image", image_id], timeout=600)
    expected_repository = account + ".dkr.ecr." + REGION + ".amazonaws.com/" + REPOSITORY
    metadata = commands.aws("ecr", "describe-repositories", "--repository-names", REPOSITORY)
    repositories = metadata.get("repositories", [])
    if len(repositories) != 1 or repositories[0].get("repositoryUri") != expected_repository:
        raise DeploymentError("The ECR repository differs from the bootstrapped account/region")
    if repositories[0].get("imageTagMutability") != "IMMUTABLE":
        raise DeploymentError("ECR image tags must remain immutable")
    host = commands.docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}").strip()
    if not host.startswith(("unix://", "npipe://")):
        raise DeploymentError("This helper only builds/pushes through a local Docker engine")
    registry = expected_repository.split("/", 1)[0]
    tag = "build-" + time.strftime("%Y%m%d%H%M%S", time.gmtime()) + "-" + uuid4().hex[:8]
    tagged = expected_repository + ":" + tag
    commands.docker("tag", image_id, tagged)
    private_directory = commands.root / ".tools/aws"
    private_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="docker-auth-", dir=private_directory) as config:
        token = commands.aws("ecr", "get-login-password", text=True)
        try:
            commands.docker("--config", config, "--host", host, "login", "--username", "AWS", "--password-stdin", registry, data=token + "\n")
        finally:
            token = None
        commands.docker("--config", config, "--host", host, "push", tagged)
    result = commands.aws("ecr", "describe-images", "--repository-name", REPOSITORY, "--image-ids", "imageTag=" + tag)
    images = result.get("imageDetails", [])
    if len(images) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", images[0].get("imageDigest", "")):
        raise DeploymentError("ECR did not return the pushed immutable image digest")
    return validate_image(expected_repository + "@" + images[0]["imageDigest"], account)


def validate_service_url(url):
    endpoint = urlparse(url)
    if endpoint.scheme != "https" or not re.fullmatch(r"[a-z0-9]+\.lambda-url\.ap-southeast-1\.on\.aws", endpoint.hostname or "") or endpoint.port or endpoint.username or endpoint.password or endpoint.path not in ("", "/") or endpoint.query or endpoint.fragment:
        raise DeploymentError("Expected the Singapore Lambda Function URL without credentials or extra path")
    return url.rstrip("/")


def observe(commands, account, *, expected=None):
    function = current_function(commands)
    if function is None:
        return {"provider": "aws", "region": REGION, "deployed": False,
                "note": "The expected function was not found; no account-wide inventory was performed"}
    config = function.get("Configuration", {})
    concurrency = current_concurrency(commands)
    url = validate_service_url(commands.aws("lambda", "get-function-url-config", "--function-name", FUNCTION)["FunctionUrl"])
    image = function.get("Code", {}).get("ResolvedImageUri")
    validate_image(image, account)
    paused = concurrency == 0
    runtime = config.get("Environment", {}).get("Variables", {})
    if expected:
        if image != expected["image_uri"] or paused != bool(expected.get("paused")):
            raise DeploymentError("Live Lambda image or pause state differs from the applied deployment")
        target = 0 if expected.get("paused") else expected["reserved_concurrency"]
        if concurrency != target:
            raise DeploymentError("Live reserved concurrency differs from the applied configuration")
        if runtime.get("STORAGE_MODE") != "dynamodb" or runtime.get("LLM_PROVIDER") != "none":
            raise DeploymentError("Live storage/generation settings differ from the reviewed configuration")
    import httpx
    status, healthy, last_error_type = None, False, None
    deadline = time.monotonic() + (90 if expected else 10)
    with httpx.Client(timeout=35 if expected else 15, trust_env=False, follow_redirects=False) as client:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                response = client.get(url + "/health", timeout=min(35 if expected else 15, remaining))
            except httpx.HTTPError as error:
                # New Function URLs and cold starts can fail transiently even
                # after Terraform has successfully applied the control plane.
                status, healthy, last_error_type = None, False, type(error).__name__
                if not expected:
                    break
            else:
                status, last_error_type = response.status_code, None
                healthy = status == 429 if paused else (status == 200 and response.json().get("storage_mode") == "dynamodb")
            remaining = deadline - time.monotonic()
            if healthy or remaining <= 0:
                break
            time.sleep(min(2, remaining))
    if expected and not healthy:
        cause = last_error_type or ("HTTP " + str(status) if status is not None else "deadline expired")
        raise DeploymentError("Live health did not confirm concurrency-zero throttling or active DynamoDB storage after bounded retries (" + cause + "); the applied control-plane change was not rolled back")
    report = {"provider": "aws", "region": REGION, "account_id": account, "deployed": True,
              "function_name": FUNCTION, "url": url, "image_uri": image,
              "paused": paused, "reserved_concurrency": concurrency, "health_http_status": status,
              "health_verified": healthy, "verification_pending": not healthy, "health_last_error_type": last_error_type, "data_retained": True, "ai_enabled": runtime.get("LLM_PROVIDER", "none") != "none",
              "monitoring": "Local Prometheus/Grafana; no hosted monitoring resources",
              "note": "-1 uses the account's shared concurrency pool and is not a per-function cost cap. Pausing blocks new invocations; in-flight work may finish. Retained storage can still incur costs."}
    private_write(commands.root / ".tools/aws-service-state.json", report)
    return report



def record_applied(commands, account, values, outputs):
    # A successful guarded apply proves the deployment exists even if a newly
    # created URL is not reachable yet. Persist enough for the stop helper now;
    # this record deliberately makes no successful health-verification claim.
    paused = bool(values.get("paused")) or values.get("reserved_concurrency") == 0
    report = {"provider": "aws", "region": REGION, "account_id": account,
              "deployed": True, "function_name": FUNCTION, "table_name": FUNCTION + "-tickets",
              "image_uri": validate_image(values["image_uri"], account), "paused": paused,
              "reserved_concurrency": 0 if paused else values["reserved_concurrency"],
              "data_retained": True, "ai_enabled": False,
              "health_verified": False, "verification_pending": True, "health_http_status": None,
              "state_source": "successful_guarded_terraform_apply",
              "note": "Applied configuration recorded for safe stopping; live service/HTTP verification is still pending"}
    output = outputs.get("service_url", {}) if isinstance(outputs, dict) else {}
    if isinstance(output, dict) and not output.get("sensitive") and isinstance(output.get("value"), str):
        try:
            report["url"] = validate_service_url(output["value"])
        except (DeploymentError, ValueError):
            pass  # Keep the proven-existence record even if an output needs review.
    private_write(commands.root / ".tools/aws-deployment.json", report)
    return report


def change_pause(commands, account, paused):
    values = read_settings(commands.root, "app", required=True)
    validate_image(values.get("image_uri"), account)
    if current_function(commands) is None:
        raise DeploymentError("There is no existing function to pause/resume; deployment is a separate step")
    values["paused"] = paused
    if not paused:
        quota = commands.aws("lambda", "get-account-settings")
        requested = commands.args.reserved_concurrency or "auto"
        values["reserved_concurrency"] = choose_concurrency(quota, current_concurrency(commands), requested)
    else:
        values.setdefault("reserved_concurrency", -1)
        # Persist the conservative stop intent before applying. A failed partial
        # operation must not make the next ordinary deployment resume the site.
        private_write(settings_path(commands.root, "app"), "".join(key + " = " + json.dumps(value) + "\n" for key, value in sorted(values.items())))
    outputs = plan_apply(commands, "app", values, account, scaling_only=True)
    record_applied(commands, account, values, outputs)
    report = observe(commands, account, expected=values)
    private_write(commands.root / ".tools/aws-deployment.json", report)
    return report


def deploy(commands, account, quota):
    saved = read_settings(commands.root, "app")
    function = current_function(commands)
    if function is not None and not saved:
        raise DeploymentError("An existing function was found; restore its private settings/state rather than recreate its configuration")
    active_concurrency = current_concurrency(commands) if function is not None else -1
    # A manual emergency throttle is also respected by ordinary redeployment.
    paused = bool(saved.get("paused", False)) or active_concurrency == 0 or saved.get("reserved_concurrency") == 0
    desired = commands.args.reserved_concurrency or (str(saved["reserved_concurrency"]) if saved.get("reserved_concurrency") in (-1, 1, 2) else "auto")
    reservation = choose_concurrency(quota, active_concurrency, desired)
    image = push_image(commands, account)
    # This explicit step preserves existing parameters. Never pass --overwrite.
    commands.run([sys.executable, "scripts/upload_aws_secrets.py", "--region", REGION])
    values = {**saved, "region": REGION, "image_uri": image, "enable_bedrock": False,
              "protect_ticket_data": True, "paused": paused, "reserved_concurrency": reservation,
              "manager_refresh_seconds": 0, "queue_limit": 20}
    outputs = plan_apply(commands, "app", values, account)
    record_applied(commands, account, values, outputs)
    report = observe(commands, account, expected=values)
    private_write(commands.root / ".tools/aws-deployment.json", report)
    return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stage", choices=("preflight", "bootstrap", "deploy", "pause", "resume", "status"), default="preflight")
    result.add_argument("--profile", default="ticketpilot")
    result.add_argument("--terraform-profile", help="Existing SDK/credential_process profile; otherwise prefer PROFILE-terraform if already configured")
    result.add_argument("--region", default=REGION, choices=(REGION,))
    result.add_argument("--account-id", help="Optional expected 12-digit account, checked before any mutation")
    result.add_argument("--local-image", default="ticketpilot-aws-lambda:local")
    result.add_argument("--skip-build", action="store_true", help="Validate and promote an already-built local Lambda image")
    result.add_argument("--reserved-concurrency", choices=("auto", "-1", "1", "2"))
    result.add_argument("--budget-alert-email", default=None, help="Optional explicit recipient for the bootstrap monthly cost alert")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.account_id:
        validate_account(args.account_id)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.profile):
        raise DeploymentError("Use an existing named AWS profile")
    if args.terraform_profile and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.terraform_profile):
        raise DeploymentError("Use an existing named Terraform AWS profile")
    commands = Commands(args)
    account = identify(commands)
    if args.stage == "status":
        print(json.dumps(observe(commands, account), indent=2))
        return 0
    if args.stage == "preflight":
        quota = preflight(commands, account, terraform=True)
        print(json.dumps({"provider": "aws", "profile": args.profile, "terraform_profile": commands.terraform_profile,
                          "region": REGION, "read_access": "available", "regional_concurrency": quota.get("AccountLimit", {}),
                          "note": "Read checks do not prove create permissions, Free plan eligibility, credit balance or expiry. No plan upgrade was performed."}, indent=2))
        return 0
    with operation_lock(ROOT):
        if args.stage in ("pause", "resume"):
            bridge = commands.aws("sts", "get-caller-identity", profile=commands.choose_terraform_profile())
            if bridge.get("Account") != account:
                raise DeploymentError("The Terraform profile belongs to another AWS account")
            report = change_pause(commands, account, args.stage == "pause")
        else:
            quota = preflight(commands, account, terraform=True)
            private_write(ROOT / ".tools/aws-account.json", {"account_id": account, "region": REGION})
            if args.stage == "bootstrap":
                values = {**read_settings(ROOT, "bootstrap"), "region": REGION, "monthly_target_usd": 10}
                if args.budget_alert_email is not None:
                    values["budget_alert_email"] = args.budget_alert_email
                plan_apply(commands, "bootstrap", values, account)
                report = {"provider": "aws", "stage": "bootstrap", "region": REGION,
                          "budget_alert_configured": bool(values.get("budget_alert_email")),
                          "note": "An optional budget is an alert, not a spending cap. Lambda has not been deployed by this stage."}
            else:
                report = deploy(commands, account, quota)
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeploymentError, subprocess.SubprocessError, OSError, ValueError, KeyError) as error:
        message = str(error) if isinstance(error, DeploymentError) else type(error).__name__
        print("AWS operation stopped: " + message, file=sys.stderr)
        raise SystemExit(1)
