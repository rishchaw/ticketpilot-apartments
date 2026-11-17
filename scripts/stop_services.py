"""Stop TicketPilot's local workloads and pause its existing GCP service.

Preserves real app/cloud data. The optional owned kind demo and its fictional
PVC data are disposable; stopping it deletes only that verified demo cluster.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def checked(command, log):
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.SubprocessError) as error:
        return {"stopped": False, "error": type(error).__name__}
    log.parent.mkdir(exist_ok=True)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    return {"stopped": result.returncode == 0, "exit_code": result.returncode,
            "private_log": str(log.relative_to(ROOT))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Existing GCP project; otherwise read the private local deployment record")
    parser.add_argument("--region", default="asia-southeast1")
    parser.add_argument("--local-only", action="store_true", help="Stop Docker/kind only; do not contact GCP")
    args = parser.parse_args(argv)
    if args.project and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", args.project):
        parser.error("Use a valid GCP project ID")
    if args.region != "asia-southeast1":
        parser.error("This project's recorded cloud deployment is in Singapore")
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
        report["docker_compose"] = checked(
            ["docker", "compose", "--profile", "local", "stop"],
            tools / "stop-services-docker.log")
        if ownership.exists():
            report["kubernetes_demo"] = checked(
                [sys.executable, "scripts/kubernetes_local.py", "stop"],
                tools / "stop-services-kubernetes.log")
        else:
            report["kubernetes_demo"] = {"skipped": "No owned local demo record; no other cluster was touched"}
    if args.local_only:
        report["gcp"] = {"skipped": "Explicit --local-only; cloud state was not changed or checked"}
    else:
        record = tools / "gcp-deployment.json"
        project = args.project
        if not project and record.exists():
            project = json.loads(record.read_text(encoding="utf-8"))["project"]
        if project:
            report["gcp"] = checked(
                [sys.executable, "scripts/deploy_gcp.py", "--project", project,
                 "--region", args.region, "--stage", "pause"],
                tools / "stop-services-gcp.log")
        else:
            report["gcp"] = {"skipped": "No private cloud deployment record; use --project to pause an existing deployment"}
    report["data"] = "Real Compose volumes/Firestore/secrets/images retained; only the owned kind demo is disposable"
    tools.mkdir(exist_ok=True)
    (tools / "stop-services.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if any(isinstance(value, dict) and value.get("stopped") is False for value in report.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
