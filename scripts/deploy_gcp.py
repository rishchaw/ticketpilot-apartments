"""Low-idle-cost Cloud Run deployment using local ADC and Terraform.

Default stage is read-only preflight. Explicit bootstrap/deploy/all stages apply
reviewed saved plans. They never change the billing plan or organization policies.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
CONFIG = "ticketpilot-gcp"


def run(command, *, capture=False, data=None, cwd=ROOT, retry_throttling=False):
    attempts = 5 if retry_throttling else 1
    for attempt in range(attempts):
        result = subprocess.run(
            [str(value) for value in command], cwd=cwd, env=environment(),
            input=data, capture_output=capture, text=True, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() if capture else ""
        rate_limited = capture and ("RATE_LIMIT_EXCEEDED" in result.stderr or
                                    "RESOURCE_EXHAUSTED" in result.stderr)
        if rate_limited and attempt + 1 < attempts:
            print("Google API throttled this request; retrying with backoff.", file=sys.stderr)
            time.sleep(min(5 * 2 ** attempt, 30))
            continue
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{Path(str(command[0])).name} command failed ({result.returncode})")
    raise RuntimeError("Google API remained throttled.")


def environment():
    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = sys.executable
    env["CLOUDSDK_CORE_DISABLE_USAGE_REPORTING"] = "true"
    env["CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK"] = "true"
    return env


def gcloud_path():
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    pointer = TOOLS / "gcloud-path.txt"
    if not found and pointer.exists():
        found = pointer.read_text().strip()
    if not found or not Path(found).is_file():
        raise RuntimeError("Install the official Google Cloud CLI and complete browser login first.")
    return found


def cloud(args, *command, json_result=True, data=None):
    cmd = [gcloud_path(), f"--configuration={CONFIG}", *command,
           f"--project={args.project}", "--quiet"]
    if json_result:
        cmd.append("--format=json")
    output = run(cmd, capture=True, data=data, retry_throttling=True)
    return json.loads(output or "{}") if json_result else output


def terraform():
    found = shutil.which("terraform")
    local = TOOLS / ("terraform.exe" if os.name == "nt" else "terraform")
    if not found and local.is_file():
        found = str(local)
    if not found:
        raise RuntimeError("Terraform is required; see docs/GCP_DEPLOYMENT.md.")
    return found


def preflight(args):
    info = cloud(args, "projects", "describe", args.project)
    if info.get("lifecycleState") != "ACTIVE":
        raise RuntimeError("The selected project is not ACTIVE.")
    billing = cloud(args, "billing", "projects", "describe", args.project)
    if billing.get("billingEnabled") is not True:
        raise RuntimeError("Link existing trial billing in the console; this script never upgrades billing.")
    policy = cloud(args, "resource-manager", "org-policies", "describe",
                   "iam.allowedPolicyMemberDomains", "--effective")
    rules = policy.get("listPolicy", {})
    if rules and rules.get("allValues") != "ALLOW":
        raise RuntimeError("Public access needs organization-policy review; no policy will be changed.")
    billing_id = billing.get("billingAccountName", "").removeprefix("billingAccounts/")
    print(json.dumps({"project": args.project, "region": args.region,
                      "project_active": True, "billing_linked": True,
                      "budget_alert_usd": args.budget_usd, "billing_plan_changed": False}))
    return args.billing_account or billing_id


def tfvars(folder, values):
    # Plain .tfvars is ignored; no credentials or secret values belong here.
    folder.mkdir(parents=True, exist_ok=True)
    content = "# Local deployment settings; do not publish.\n"
    content += "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items())
    (folder / "ticketpilot.generated.tfvars").write_text(content, encoding="utf-8")


def plan_apply(stage, values):
    folder = ROOT / "infra" / "gcp" / stage
    tfvars(folder, values)
    tool = terraform()
    run([tool, "init", "-input=false", "-lockfile=readonly"], cwd=folder)
    plan = TOOLS / f"gcp-{stage}.tfplan"
    run([tool, "plan", "-input=false", "-var-file=ticketpilot.generated.tfvars", "-out", plan], cwd=folder)
    document = json.loads(run([tool, "show", "-json", plan], cwd=folder, capture=True))
    changed = []
    allowed = {
        "google_project_service", "google_artifact_registry_repository",
        "google_secret_manager_secret", "google_billing_budget",
    } if stage == "bootstrap" else {
        "google_service_account", "google_project_iam_member",
        "google_secret_manager_secret_iam_member", "google_firestore_database",
        "google_cloud_run_v2_service", "google_cloud_run_v2_service_iam_member",
    }
    for item in document.get("resource_changes", []):
        actions = item["change"]["actions"]
        if item.get("mode") == "data" or actions == ["no-op"]:
            continue
        if item["type"] not in allowed or "delete" in actions or actions not in (["create"], ["update"]):
            raise RuntimeError(f"Unexpected/destructive plan at {item['address']}: {actions}")
        after = item["change"].get("after") or {}
        if item["type"] == "google_cloud_run_v2_service":
            template = after["template"][0]
            limits = template["containers"][0]["resources"][0]
            if after["scaling"][0]["max_instance_count"] != 1 or template["scaling"][0]["min_instance_count"] != 0:
                raise RuntimeError("Cloud Run scaling differs from the low-cost configuration.")
            if not limits["cpu_idle"] or limits["startup_cpu_boost"]:
                raise RuntimeError("Cloud Run must use request-based CPU without startup boost.")
            runtime = {v["name"]: v.get("value") for v in template["containers"][0]["env"]}
            if runtime.get("LLM_PROVIDER") != "none" or runtime.get("STORAGE_MODE") != "firestore":
                raise RuntimeError("AI must stay disabled and durable Firestore storage enabled.")
        changed.append({"address": item["address"], "actions": actions})
    (TOOLS / f"gcp-{stage}-plan-summary.json").write_text(json.dumps(changed, indent=2))
    print(json.dumps({"reviewed_plan": stage, "changes": changed}, indent=2))
    run([tool, "apply", "-input=false", plan], cwd=folder)
    return json.loads(run([tool, "output", "-json"], cwd=folder, capture=True))


def local_secrets():
    values = {}
    path = ROOT / ".env"
    if not path.is_file():
        raise RuntimeError("Create local .env using scripts/setup_local.py first.")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    for key in ("ADMIN_TOKEN", "METRICS_TOKEN"):
        if len(values.get(key, "")) < 24:
            raise RuntimeError(f"Generate a strong local {key} before deployment.")
    return values


def upload_secrets(args):
    values = local_secrets()
    for key, name in (("ADMIN_TOKEN", "admin"), ("METRICS_TOKEN", "metrics")):
        secret = f"ticketpilot-apartments-{name}"
        versions = cloud(args, "secrets", "versions", "list", secret)
        if versions:
            latest = max(versions, key=lambda v: int(v["name"].rsplit("/", 1)[-1]))
            if latest.get("state") != "ENABLED":
                raise RuntimeError(f"The latest version for {secret} is not enabled; review it explicitly.")
            # Preserve existing cloud credentials; never silently rotate a running service.
            print(f"Preserving existing enabled version for {secret}.")
            continue
        cloud(args, "secrets", "versions", "add", secret, "--data-file=-",
              data=values[key], json_result=False)
        print(f"Created the initial version for {secret}; value withheld.")


def database_mode(args):
    folder = ROOT / "infra" / "gcp" / "app"
    state_path = folder / "terraform.tfstate"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        if any(r.get("type") == "google_firestore_database" and r.get("name") == "tickets"
               for r in state.get("resources", [])):
            return True
    result = cloud(args, "firestore", "databases", "list")
    databases = result if isinstance(result, list) else result.get("databases", [])
    if not databases:
        return True
    default = next((d for d in databases if d["name"].endswith("/(default)")), None)
    if not default:
        raise RuntimeError("Existing named database found; review free-quota eligibility before creating another.")
    if default.get("type") != "FIRESTORE_NATIVE" or default.get("locationId") != args.region:
        raise RuntimeError("Existing default database has a different type/location; it will not be modified.")
    if default.get("databaseEdition", "STANDARD") != "STANDARD":
        raise RuntimeError("Existing database edition needs review.")
    print("Using the existing default Firestore database without managing or modifying it.")
    return False


def build_push(args, repository):
    image = repository + "/app"
    tag = image + ":poc-" + time.strftime("%Y%m%d%H%M%S", time.gmtime())
    run(["docker", "image", "inspect", args.local_image], capture=True)
    # Temporary Docker credential config prevents a persistent access token in ~/.docker/config.json.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ticketpilot-docker-", dir=TOOLS) as config:
        token = cloud(args, "auth", "print-access-token", json_result=False)
        run(["docker", "--config", config, "login", "-u", "oauth2accesstoken",
             "--password-stdin", f"{args.region}-docker.pkg.dev"], capture=True, data=token)
        token = None
        run(["docker", "tag", args.local_image, tag])
        run(["docker", "--config", config, "push", tag])
    metadata = cloud(args, "artifacts", "docker", "images", "describe", tag)
    digest = metadata["image_summary"]["digest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Registry returned an invalid image digest.")
    return image + "@" + digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", default="asia-southeast1")
    parser.add_argument("--budget-usd", type=int, default=10, choices=range(1, 101), metavar="USD")
    parser.add_argument("--billing-account", default="")
    parser.add_argument("--stage", choices=["preflight", "bootstrap", "deploy", "all"], default="preflight")
    parser.add_argument("--local-image", default="ticketpilot-gcp:local",
                        help="Already-built and emulator-tested Dockerfile.gcp image")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", args.project):
        parser.error("Use a Google Cloud project ID.")
    if args.region != "asia-southeast1":
        parser.error("This demonstration is configured and cost-reviewed for Singapore.")
    TOOLS.mkdir(exist_ok=True)
    billing_id = preflight(args)
    if args.stage == "preflight":
        return 0
    if args.stage in ("bootstrap", "all"):
        plan_apply("bootstrap", {"project_id": args.project, "region": args.region,
                                "create_budget": True, "billing_account_id": billing_id,
                                "budget_amount_usd": args.budget_usd})
    if args.stage == "bootstrap":
        return 0
    # No transient SQLite data; inspect existing databases before provisioning.
    manage = database_mode(args)
    upload_secrets(args)
    repository = f"{args.region}-docker.pkg.dev/{args.project}/ticketpilot-apartments"
    image = build_push(args, repository)
    outputs = plan_apply("app", {"project_id": args.project, "region": args.region,
                                "image_uri": image, "manage_database": manage})
    url = outputs["service_url"]["value"]
    run([sys.executable, "scripts/smoke_cloud.py", url, "--expected-storage=firestore"])
    run([sys.executable, "scripts/validate_gcp_deployment.py", "--url", url, "--project", args.project])
    cloud(args, "artifacts", "docker", "tags", "add", image, repository + "/app:deployed",
          json_result=False)
    report = {"project": args.project, "region": args.region, "url": url, "image": image,
              "storage": "firestore", **outputs["runtime_configuration"]["value"],
              "budget_alert_usd": args.budget_usd}
    (TOOLS / "gcp-deployment.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(f"Deployment stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
