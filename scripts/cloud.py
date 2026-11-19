"""One cloud provider at a time, using each provider's native deployment path.

Examples: python scripts/cloud.py aws deploy --confirm-other-offline
          python scripts/cloud.py aws pause
          python scripts/cloud.py gcp status --project YOUR-PROJECT-ID

An offline attestation is weaker than an authenticated control-plane observation;
reports distinguish them. Monitoring is optional, local and stopped on pause.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import deploy_aws as aws_native

PROVIDERS = ("aws", "gcp")
ACTIONS = ("deploy", "pause", "resume", "status", "monitor-start", "monitor-stop")
REGIONS = {"aws": "ap-southeast-1", "gcp": "asia-southeast1"}
GCP_SERVICE = "ticketpilot-apartments"
FIRESTORE_EMULATOR = "gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators"


class CloudError(Exception):
    pass


class ControlUnavailable(CloudError):
    """No authenticated observation was obtained; this never means offline."""


def now():
    return datetime.now(timezone.utc).isoformat()


class Runner:
    def __init__(self, root=ROOT):
        self.root = root

    def run(self, command, *, env=None, timeout=1800):
        result = subprocess.run(list(map(str, command)), cwd=self.root, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            # Keep failed native diagnostics private instead of discarding the
            # evidence needed to troubleshoot; never upload this ignored file.
            aws_native.private_write(self.root / ".tools/cloud-last-command-error.log",
                                     (result.stdout or "") + (result.stderr or ""))
            raise CloudError(Path(str(command[0])).name + " exited " + str(result.returncode) + "; inspect private .tools/cloud-last-command-error.log before retrying")
        return result.stdout

    def native(self, provider, stage, args):
        command = native_command(self.root, provider, stage, args)
        if stage != "status":
            print("Running " + provider + " stage " + stage + ".", flush=True)
        output = self.run(command)
        if output and stage != "status":
            print(output.rstrip(), flush=True)
        return output

    def aws(self, args, *command):
        executable = shutil.which("aws")
        if not executable:
            raise ControlUnavailable("AWS CLI is unavailable")
        try:
            output = self.run([executable, *command, "--profile", args.profile, "--region", REGIONS["aws"],
                               "--no-cli-pager", "--output", "json"],
                              env=aws_native.scoped_environment(os.environ, args.profile), timeout=90)
            return json.loads(output.strip() or "{}")
        except (CloudError, OSError, subprocess.SubprocessError, ValueError) as error:
            raise ControlUnavailable("AWS control-plane read unavailable") from error

    def gcp(self, context):
        from scripts import deploy_gcp as gcp_native
        try:
            return gcp_native.cloud(SimpleNamespace(project=context["project"], region=REGIONS["gcp"]),
                                    "run", "services", "describe", GCP_SERVICE, "--region=" + REGIONS["gcp"])
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
            raise ControlUnavailable("GCP control-plane read unavailable") from error


def native_command(root, provider, stage, args):
    command = [sys.executable, str(root / "scripts" / ("deploy_" + provider + ".py")), "--stage", stage]
    if provider == "aws":
        command += ["--profile", args.profile, "--region", REGIONS["aws"]]
        if args.terraform_profile:
            command += ["--terraform-profile", args.terraform_profile]
        if args.account_id:
            command += ["--account-id", args.account_id]
        if stage == "bootstrap" and args.budget_alert_email:
            command += ["--budget-alert-email", args.budget_alert_email]
        if stage == "deploy":
            command += ["--local-image", args.local_image or "ticketpilot-aws-lambda:local"]
            if args.skip_build:
                command.append("--skip-build")
        if stage in ("deploy", "resume") and args.reserved_concurrency:
            command += ["--reserved-concurrency", args.reserved_concurrency]
    else:
        if not args.project:
            raise CloudError("Provide --project or restore the private GCP deployment record")
        command += ["--project", args.project, "--region", REGIONS["gcp"]]
        if stage == "all":
            command += ["--local-image", args.local_image or "ticketpilot-gcp:local", "--budget-usd", str(args.budget_usd)]
            if args.billing_account:
                command += ["--billing-account", args.billing_account]
        if stage in ("all", "deploy") and getattr(args, "validate_tenant_workflow", False):
            command += ["--validate-tenant-workflow", "--credentials-file", str(args.credentials_file)]
    if stage in ("deploy", "all"):
        if getattr(args, "apartment_units", None) is not None:
            command += ["--apartment-units", args.apartment_units]
        if getattr(args, "leave_paused", False):
            command.append("--leave-paused")
    return command


def read_json(path):
    if path.is_symlink():
        raise CloudError("Refusing a symlink at a private deployment record")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise CloudError("A deployment record is unreadable; restore it rather than assuming the service is offline") from error
    if not isinstance(value, dict):
        raise CloudError("Unexpected deployment record schema")
    return value


def context_for(root, provider, *, required=False):
    deployment = root / ".tools" / (provider + "-deployment.json")
    state = root / ".tools" / (provider + "-service-state.json")
    candidates = [(path, read_json(path)) for path in (deployment, state) if path.exists()]
    if not candidates:
        if required:
            raise CloudError("Restore the existing " + provider + " deployment record first")
        return None
    combined = {}
    for path, value in sorted(candidates, key=lambda item: item[0].stat().st_mtime_ns):
        if value.get("region", REGIONS[provider]) != REGIONS[provider]:
            raise CloudError("Recorded provider region differs from this Singapore deployment")
        for key in ("project", "account_id"):
            if key in combined and key in value and combined[key] != value[key]:
                raise CloudError("Deployment and service-state identity records disagree")
        if combined.get("url") and value.get("url") and combined["url"].rstrip("/") != value["url"].rstrip("/"):
            raise CloudError("Deployment and service-state URLs disagree")
        combined.update(value)
    if provider == "gcp":
        project = combined.get("project", combined.get("project_id", ""))
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
            raise CloudError("The private GCP record needs its existing project ID")
        combined["project"] = project
    elif combined.get("account_id"):
        aws_native.validate_account(combined["account_id"])
    combined["provider"] = provider
    return combined


def valid_url(provider, address):
    if not isinstance(address, str):
        raise CloudError("A provider URL is missing")
    parsed = urlparse(address)
    allowed = (r"[a-z0-9]+\.lambda-url\.ap-southeast-1\.on\.aws" if provider == "aws" else
               r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app")
    if parsed.scheme != "https" or not re.fullmatch(allowed, parsed.hostname or "") or parsed.port or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise CloudError("Use the existing HTTPS provider base URL without credentials or an extra path")
    return address.rstrip("/")


def recorded_urls(provider, context):
    urls = {valid_url(provider, context["url"])} if context.get("url") else set()
    for entry in context.get("verified_urls", []):
        if not isinstance(entry, dict) or "url" not in entry:
            raise CloudError("Unexpected recorded service URL schema")
        urls.add(valid_url(provider, entry["url"]))
    return urls


def public_observations(provider, urls, *, offline):
    import httpx
    if not urls or len(urls) > 20:
        raise CloudError("Expected a bounded set of known service URLs")
    observations = []
    expected = {404, 429} if provider == "aws" else {404, 503}
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        for address in sorted(urls):
            try:
                response = client.get(valid_url(provider, address) + "/health")
            except httpx.HTTPError as error:
                raise CloudError("Network/TLS/DNS failure is not proof that the other provider is offline") from error
            observations.append({"url": address, "health_http_status": response.status_code})
            if offline and response.status_code not in expected:
                raise CloudError("A known URL did not show the expected paused/unavailable response")
    return observations


def authenticated_state(runner, provider, context, args):
    urls = recorded_urls(provider, context)
    if provider == "aws":
        identity = runner.aws(args, "sts", "get-caller-identity")
        if context.get("account_id") and identity.get("Account") != context["account_id"]:
            raise CloudError("The AWS profile does not match the other provider's recorded AWS account")
        concurrency = runner.aws(args, "lambda", "get-function-concurrency", "--function-name", aws_native.FUNCTION).get("ReservedConcurrentExecutions", -1)
        endpoint = runner.aws(args, "lambda", "get-function-url-config", "--function-name", aws_native.FUNCTION)
        live_url = valid_url("aws", endpoint["FunctionUrl"])
        if context.get("url") and valid_url("aws", context["url"]) != live_url:
            raise CloudError("The authenticated function URL does not match the recorded AWS deployment")
        urls.add(live_url)
        return {"paused": concurrency == 0, "reserved_concurrency": concurrency,
                "known_urls": urls, "authenticated_cloud_read": True}
    service = runner.gcp(context)
    if service.get("metadata", {}).get("name") != GCP_SERVICE:
        raise CloudError("Cloud Run returned an unexpected service identity")
    annotations = service["metadata"].get("annotations", {})
    mode = annotations.get("run.googleapis.com/scalingMode", "automatic")
    count = annotations.get("run.googleapis.com/manualInstanceCount")
    traffic = service.get("status", {}).get("traffic", [])
    tagged = any(item.get("tag") for item in traffic)
    live_urls = set()
    if service.get("status", {}).get("url"):
        live_urls.add(valid_url("gcp", service["status"]["url"]))
    encoded = annotations.get("run.googleapis.com/urls", "[]")
    try:
        extras = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise CloudError("Cloud Run URL metadata could not be verified") from error
    if not isinstance(extras, list):
        raise CloudError("Cloud Run URL metadata must be a list")
    live_urls.update(valid_url("gcp", address) for address in extras)
    if context.get("url") and valid_url("gcp", context["url"]) not in live_urls:
        raise CloudError("The authenticated service URLs do not match the recorded GCP deployment")
    urls.update(live_urls)
    return {"paused": mode == "manual" and str(count) == "0" and not tagged,
            "scaling_mode": mode, "manual_instance_count": count, "traffic_tags_present": tagged,
            "known_urls": urls, "authenticated_cloud_read": True}


def guard_other_provider(runner, args):
    other = "gcp" if args.provider == "aws" else "aws"
    context = context_for(runner.root, other)
    if context is None:
        return {"other_provider": other, "evidence": "no_local_deployment_record",
                "note": "No account-wide claim is made; this guard covers this project's recorded deployments"}
    try:
        observed = authenticated_state(runner, other, context, args)
    except ControlUnavailable as error:
        if not args.confirm_other_offline:
            raise CloudError("Cannot authenticate the other provider's pause state. Renew its login, or explicitly use --confirm-other-offline only after independently confirming it is paused") from error
        if context.get("paused") is not True:
            raise CloudError("Operator attestation requires an existing recorded paused state; no active or unknown record can be overridden") from error
        urls = recorded_urls(other, context)
        public = public_observations(other, urls, offline=True)
        proof = {"other_provider": other, "paused": True, "evidence": "operator_attestation_and_fresh_public_http",
                 "authenticated_cloud_read": False, "verified_urls": public,
                 "note": "Explicit operator attestation plus a recorded pause and unavailable known URLs; not an authenticated cloud-state verification"}
    else:
        if observed.get("paused") is not True:
            raise CloudError("The other provider is active or has unverified traffic; pause it before deploying/resuming this provider")
        public = public_observations(other, observed.pop("known_urls"), offline=True)
        proof = {"other_provider": other, **observed, "evidence": "authenticated_cloud_read_and_fresh_public_http", "verified_urls": public}
    proof["checked_at_utc"] = now()
    aws_native.private_write(runner.root / ".tools/cloud-provider-guard.json", proof)
    return proof


def gcp_status(runner, args):
    context = context_for(runner.root, "gcp", required=True)
    if args.project and args.project != context["project"]:
        raise CloudError("The supplied GCP project differs from the existing deployment record")
    observed = authenticated_state(runner, "gcp", context, args)
    public = public_observations("gcp", observed.pop("known_urls"), offline=observed["paused"])
    report = {"provider": "gcp", "project": context["project"], "region": REGIONS["gcp"],
              "url": valid_url("gcp", context["url"]), **observed,
              "verified_urls": public, "checked_at_utc": now(), "action": "status",
              "note": "Read-only service observation; no resume or provisioning was requested"}
    aws_native.private_write(runner.root / ".tools/gcp-service-state.json", report)
    return report


def docker_offline(stderr):
    text = (stderr or "").lower()
    return any(marker in text for marker in ("the system cannot find the file specified",
               "cannot connect to the docker daemon", "connect: no such file or directory"))


def monitor_stop(runner):
    docker = shutil.which("docker")
    if not docker:
        raise CloudError("Docker CLI is unavailable; local monitoring stop was not verified")
    probe = subprocess.run([docker, "info", "--format", "{{.OSType}}"], cwd=runner.root,
                           capture_output=True, text=True, timeout=15)
    if probe.returncode and docker_offline(probe.stderr):
        return {"stopped": True, "detail": "Docker engine is offline; it was not started"}
    if probe.returncode:
        raise CloudError("Docker access failed; a permission/error response is not proof of a stopped engine")
    env = os.environ.copy()
    # Compose interpolates disabled app definitions too. These placeholders are
    # scoped only to stopping services; they never configure an application.
    for name in ("ADMIN_TOKEN", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD"):
        env[name] = "unused-only-for-monitor-stop"
    runner.run([docker, "compose", "--file", str(runner.root / "compose.yaml"), "--project-directory", str(runner.root),
                "stop", "prometheus", "grafana"], env=env, timeout=120)
    return {"stopped": True, "detail": "Only this Compose project's Prometheus/Grafana stopped; volumes retained"}


def monitor_start(runner, args):
    context = context_for(runner.root, args.provider, required=True)
    if context.get("paused") is True:
        raise CloudError("The recorded service is paused; resume explicitly before starting cloud scrapes")
    observed = authenticated_state(runner, args.provider, context, args)
    if observed.get("paused") is not False:
        raise CloudError("Cloud monitoring needs an authenticated active service")
    url = valid_url(args.provider, context["url"])
    from dotenv import dotenv_values
    values = dotenv_values(runner.root / ".env")
    if any(not isinstance(values.get(key), str) or len(values[key]) < 24 for key in ("ADMIN_TOKEN", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD")):
        raise CloudError("Restore the existing local access codes before monitoring; this command never generates or rotates cloud secrets")
    import httpx
    with httpx.Client(timeout=35, trust_env=False, follow_redirects=False) as client:
        response = client.get(url + "/metrics", headers={"Authorization": "Bearer " + values["METRICS_TOKEN"]})
        if response.status_code != 200 or "ticketpilot_" not in response.text:
            raise CloudError("The local metrics token does not authorize the selected cloud service; no secret was changed")
    monitor_stop(runner)
    # JSON is valid YAML. Values contain only a hostname and a file reference.
    config = {"global": {"scrape_interval": "300s", "scrape_timeout": "25s"},
              "rule_files": ["/etc/prometheus/alerts.yml"],
              "scrape_configs": [{"job_name": "ticketpilot", "scheme": "https", "metrics_path": "/metrics",
                  "authorization": {"type": "Bearer", "credentials_file": "/run/secrets/metrics-token"},
                  "static_configs": [{"targets": [urlparse(url).hostname + ":443"]}]}]}
    aws_native.private_write(runner.root / "monitoring/prometheus/cloud.yml", config)
    aws_native.private_write(runner.root / ".secrets/metrics-token", values["METRICS_TOKEN"])
    env = os.environ.copy()
    env["PROMETHEUS_CONFIG"] = "./monitoring/prometheus/cloud.yml"
    docker = shutil.which("docker")
    if not docker:
        raise CloudError("Docker CLI is unavailable")
    runner.run([docker, "compose", "--file", str(runner.root / "compose.yaml"), "--project-directory", str(runner.root),
                "up", "-d", "--no-deps", "--force-recreate", "prometheus", "grafana"], env=env, timeout=300)
    report = {"provider": args.provider, "running": True, "location": "local Docker only", "scrape_interval_seconds": 300,
              "url": url, "grafana": "http://127.0.0.1:3000", "prometheus": "http://127.0.0.1:9090",
              "note": "Optional diagnostic scrapes can invoke cloud compute. Metrics are process-local and are not a durable fleet-wide total. No cloud monitoring resources were provisioned."}
    aws_native.private_write(runner.root / ".tools/cloud-monitoring.json", report)
    return report



def build_validate_gcp(runner, args):
    docker = shutil.which("docker")
    if not docker:
        raise CloudError("Start the local Docker Linux engine and install its CLI before deployment")
    image = args.local_image or "ticketpilot-gcp:local"
    runner.run([docker, "buildx", "build", "--platform", "linux/amd64", "--provenance=false", "--load",
                "-f", "Dockerfile.gcp", "-t", image, "."], timeout=1200)
    image_id = runner.run([docker, "image", "inspect", "--format", "{{.Id}}", image], timeout=30).strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise CloudError("Docker did not return the built immutable local image ID")
    # The validator uses --pull=never and owns its uniquely labeled app,
    # emulator and networks; prepare its pinned emulator image explicitly.
    runner.run([docker, "pull", FIRESTORE_EMULATOR], timeout=900)
    runner.run([sys.executable, str(runner.root / "scripts/validate_firestore_local.py"),
                "--image", image_id, "--emulator-image", FIRESTORE_EMULATOR], timeout=600)
    # Bind promotion to the exact image validated above, even if its tag moves.
    args.local_image = image_id
    return {"status": "passed", "image_id": image_id, "emulator_image": FIRESTORE_EMULATOR,
            "scope": "Credential-free local Firestore emulator; fictional data and disposable resources"}


def aws_acceptance(runner, args):
    context = context_for(runner.root, "aws", required=True)
    if context.get("paused"):
        return {"skipped": "Preserved paused deployment; no online acceptance was run"}
    url = valid_url("aws", context["url"])
    # Routine deployment/resume must work after tenants privately change their
    # passwords. It never opens the initial onboarding inventory or writes a
    # concern unless the operator explicitly requests the private workflow.
    runner.run([sys.executable, str(runner.root / "scripts/smoke_cloud.py"), url,
                "--expected-storage=dynamodb"], timeout=180)
    if not getattr(args, "validate_tenant_workflow", False):
        return {"status": "passed", "scope": "Read-only AWS health and anonymous access-denial checks",
                "tenant_workflow": "not requested; no tenant credentials read or tenant records written"}
    runner.run([sys.executable, str(runner.root / "scripts/validate_aws_deployment.py"),
                "--url", url, "--table", "ticketpilot-aws-tickets", "--function", aws_native.FUNCTION,
                "--profile", args.profile, "--region", REGIONS["aws"],
                "--credentials-file", str(args.credentials_file)], timeout=600)
    return {"status": "passed", "scope": "Explicit AWS tenant workflow acceptance and guarded synthetic cleanup",
            "tenant_workflow": "passed using operator-selected current authorized credentials"}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("provider", choices=PROVIDERS)
    result.add_argument("action", choices=ACTIONS)
    result.add_argument("--apartment-units", help="Eight unit labels, for deployment only")
    result.add_argument("--leave-paused", action="store_true", help="Prepare/deploy without enabling request serving")
    result.add_argument("--profile", default="ticketpilot", help="AWS profile for target AWS or the other-provider guard")
    result.add_argument("--terraform-profile")
    result.add_argument("--account-id")
    result.add_argument("--project", help="Existing GCP project, inferred from its private record when available")
    result.add_argument("--billing-account")
    result.add_argument("--budget-usd", type=int, default=10, choices=range(1, 11), metavar="USD")
    result.add_argument("--budget-alert-email")
    result.add_argument("--local-image")
    result.add_argument("--skip-build", action="store_true", help="Use an already-built image; GCP also skips the local emulator check, so provide a prevalidated image")
    result.add_argument("--reserved-concurrency", choices=("auto", "-1", "1", "2"))
    result.add_argument("--confirm-other-offline", action="store_true",
                        help="Explicit operator attestation, permitted only with a recorded pause and fresh unavailable known URLs when control-plane reads are unavailable")
    result.add_argument("--validate-tenant-workflow", action="store_true",
                        help="Explicitly exercise private tenant writes using current authorized credentials; supported for AWS deploy/resume and GCP deploy only")
    result.add_argument("--credentials-file", type=Path, default=ROOT / ".secrets/tenant-credentials.json",
                        help="Private current tenant inventory for explicit workflow validation; ordinary deploy/resume never reads it")
    return result


def execute(runner, args):
    if getattr(args, "apartment_units", None) is not None:
        from scripts.tenant_settings import units_csv
        try:
            args.apartment_units = units_csv(args.apartment_units)
        except ValueError as error:
            raise CloudError(str(error)) from None
    if (getattr(args, "apartment_units", None) is not None or getattr(args, "leave_paused", False)) and args.action != "deploy":
        raise CloudError("Unit settings and --leave-paused apply only to deploy; start uses resume")
    if getattr(args, "validate_tenant_workflow", False):
        if args.action not in ("deploy", "resume"):
            raise CloudError("Private tenant workflow validation is supported only during deploy/resume")
        if args.provider == "gcp" and args.action != "deploy":
            raise CloudError("GCP private tenant workflow validation requires deploy; resume performs read-only checks")
    if args.provider == "gcp" and args.action not in ("monitor-stop",):
        context = context_for(runner.root, "gcp")
        if context:
            if args.project and args.project != context["project"]:
                raise CloudError("The supplied GCP project differs from the existing deployment record")
            args.project = context["project"]
    if args.action == "status":
        if args.provider == "gcp":
            return gcp_status(runner, args)
        output = runner.native("aws", "status", args)
        return json.loads(output)
    if args.action == "monitor-stop":
        result = monitor_stop(runner)
        aws_native.private_write(runner.root / ".tools/cloud-monitoring.json", {**result, "running": False})
        return result
    if args.action == "monitor-start":
        return monitor_start(runner, args)
    if args.action == "pause":
        monitoring = None
        try:
            monitoring = monitor_stop(runner)
        except (CloudError, OSError, subprocess.SubprocessError) as error:
            monitoring = {"stopped": False, "error_type": type(error).__name__}
        # Independent cloud pause must still be attempted when local Docker fails.
        runner.native(args.provider, "pause", args)
        report = {"provider": args.provider, "action": "pause", "native_pause": "completed", "monitoring": monitoring}
        if not monitoring.get("stopped"):
            raise CloudError("Cloud pause completed, but local monitoring stop was not verified")
        return report
    proof = guard_other_provider(runner, args)
    monitor_stop(runner)
    if args.provider == "aws":
        if args.action == "deploy":
            runner.native("aws", "bootstrap", args)
        runner.native("aws", args.action, args)
        acceptance = aws_acceptance(runner, args)
    else:
        local_check = None
        if args.action == "deploy" and not args.skip_build:
            local_check = build_validate_gcp(runner, args)
        runner.native("gcp", "all" if args.action == "deploy" else "resume", args)
        acceptance = {"scope": "GCP native deployment checks", "local_validation": local_check or "Explicit --skip-build: supplied prevalidated image",
                      "tenant_workflow": "explicitly requested from native helper" if args.validate_tenant_workflow else "not requested; read-only cloud smoke"} if args.action == "deploy" else {"scope": "Native GCP resume health and read-only access verification"}
    return {"provider": args.provider, "action": args.action, "other_provider_guard": proof,
            "acceptance": acceptance, "monitoring": "stopped; opt in using monitor-start"}


@contextmanager
def dispatch_lock(root):
    path = root / ".tools/cloud-dispatch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = uuid4().hex
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise CloudError("Another cloud action holds cloud-dispatch.lock; inspect a stale lock before removing it") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(marker)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        yield
    finally:
        if path.is_file() and path.read_text(encoding="utf-8") == marker:
            path.unlink()


def main(argv=None):
    args = parser().parse_args(argv)
    runner = Runner()
    if args.action == "status":
        report = execute(runner, args)
    else:
        # Separate from each native helper's provider lock, preventing concurrent
        # provider switches through this entry point without nested-lock deadlock.
        with dispatch_lock(ROOT):
            report = execute(runner, args)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CloudError, aws_native.DeploymentError, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        message = str(error) if isinstance(error, (CloudError, aws_native.DeploymentError)) else type(error).__name__
        print("Cloud action stopped: " + message, file=sys.stderr)
        raise SystemExit(1)
