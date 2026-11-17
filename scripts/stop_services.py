"""Stop TicketPilot's local workloads and pause its known AWS/GCP services.

Preserves real app/cloud data. The optional owned kind demo and its fictional
PVC data are disposable; stopping it deletes only that verified demo cluster.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def checked(command, log, *, env=None):
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=600, env=env)
    except (OSError, subprocess.SubprocessError) as error:
        return {"stopped": False, "error": type(error).__name__}
    log.parent.mkdir(exist_ok=True)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    return {"stopped": result.returncode == 0, "exit_code": result.returncode,
            "private_log": str(log.relative_to(ROOT))}


def attempt(command, log, *, env=None):
    """A failed local/provider stop must never block another requested pause."""
    try:
        return checked(command, log, env=env)
    except Exception as error:
        return {"stopped": False, "error": type(error).__name__}


def pause_gcp(args, tools):
    try:
        record = tools / "gcp-deployment.json"
        project = args.project
        if not project and record.exists():
            project = json.loads(record.read_text(encoding="utf-8")).get("project")
            if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
                return {"stopped": False, "error": "InvalidGCPDeploymentRecord"}
        if project:
            return attempt(
                [sys.executable, "scripts/deploy_gcp.py", "--project", project,
                 "--region", args.region, "--stage", "pause"],
                tools / "stop-services-gcp.log")
        return {"skipped": "No private GCP deployment record; use --project to pause an existing deployment"}
    except Exception as error:
        return {"stopped": False, "error": type(error).__name__}


def pause_aws(args, tools):
    try:
        # An explicit AWS selection requests a pause even if the deployment
        # report is missing. The native helper still verifies existing state.
        known = args.provider == "aws"
        record = tools / "aws-deployment.json"
        if not known and record.exists():
            known = json.loads(record.read_text(encoding="utf-8")).get("deployed") is True
        if known:
            return attempt(
                [sys.executable, "scripts/deploy_aws.py", "--stage", "pause",
                 "--profile", args.profile],
                tools / "stop-services-aws.log")
        return {"skipped": "No known deployed AWS service; use --provider aws to request its existing-state pause explicitly"}
    except Exception as error:
        return {"stopped": False, "error": type(error).__name__}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Existing GCP project; otherwise read the private local deployment record")
    parser.add_argument("--region", default="asia-southeast1")
    parser.add_argument("--local-only", action="store_true", help="Stop Docker/kind only; do not contact AWS or GCP")
    parser.add_argument("--provider", choices=("aws", "gcp", "all"), default="all", help="Cloud providers to pause in addition to local workloads")
    parser.add_argument("--profile", default="ticketpilot", help="AWS profile used only for its native pause helper")
    args = parser.parse_args(argv)
    if args.project and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", args.project):
        parser.error("Use a valid GCP project ID")
    if args.region != "asia-southeast1":
        parser.error("This project's recorded cloud deployment is in Singapore")
    if not args.profile.strip():
        parser.error("Use a nonempty AWS CLI profile name")
    tools = ROOT / ".tools"
    report = {}
    engine_offline = False
    try:
        probe = subprocess.run(["docker", "info", "--format", "{{.OSType}}"],
                               cwd=ROOT, capture_output=True, text=True, timeout=15)
        offline_errors = ("the system cannot find the file specified",
                          "cannot connect to the docker daemon",
                          "connect: no such file or directory")
        engine_offline = probe.returncode != 0 and any(value in probe.stderr.lower() for value in offline_errors)
    except (OSError, subprocess.SubprocessError):
        pass  # Still try the scoped stop; never infer offline from permission/unknown failures.
    ownership = tools / "kubernetes/ownership.json"
    if engine_offline:
        report["docker_compose"] = {"stopped": True, "detail": "Docker engine is already offline; preserved volumes"}
        report["kubernetes_demo"] = {"stopped": True, "detail": "Docker engine is offline; no local kind compute is running; cluster deletion was not attempted"}
    else:
        # Compose interpolates required variables even for stop. These scoped
        # placeholders allow shutdown without .env and never reach cloud helpers
        # or any command that starts/reconfigures an application.
        stop_environment = os.environ.copy()
        for name in ("ADMIN_TOKEN", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD"):
            stop_environment[name] = "unused-only-for-compose-stop"
        report["docker_compose"] = attempt(
            ["docker", "compose", "--profile", "local", "stop"],
            tools / "stop-services-docker.log", env=stop_environment)
        if ownership.exists():
            report["kubernetes_demo"] = attempt(
                [sys.executable, "scripts/kubernetes_local.py", "stop"],
                tools / "stop-services-kubernetes.log")
        else:
            report["kubernetes_demo"] = {"skipped": "No owned local demo record; no other cluster was touched"}
    if args.local_only:
        for provider in ("gcp", "aws"):
            report[provider] = {"skipped": "Explicit --local-only; cloud state was not changed or checked"}
    else:
        report["gcp"] = pause_gcp(args, tools) if args.provider in ("gcp", "all") else {"skipped": "GCP was not selected by --provider"}
        # Independent call: a Docker, kind, GCP auth, state or pause failure
        # must not prevent the known AWS service from being paused too.
        report["aws"] = pause_aws(args, tools) if args.provider in ("aws", "all") else {"skipped": "AWS was not selected by --provider"}
    report["data"] = "Real Compose volumes, DynamoDB, Firestore, secrets/parameters and images retained; only the owned kind demo is disposable"
    tools.mkdir(exist_ok=True)
    (tools / "stop-services.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if any(isinstance(value, dict) and value.get("stopped") is False for value in report.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
