"""Exercise the GCP image against an isolated local Firestore emulator.

Only this run's uniquely labeled containers/networks are created and removed.
The app is limited to 512 MiB and 1 CPU with a read-only root and temporary /tmp.
No host credentials are mounted, no cloud project is accessed and no real data
is used. Build/pull the two images before running this checker.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from time import monotonic, sleep
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.validate_gcp_deployment import ValidationError, exercise_http, failure_details, require, tracking, write_report

LABEL = "ticketpilot.validation.run"


def docker(*arguments, check=True, timeout=90):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        # Never echo command arguments/environment: even test access codes stay private.
        raise ValidationError("Docker " + arguments[0] + " failed; inspect the local validation log")
    return result


def inspect_container(name):
    result = docker("inspect", name, check=False, timeout=15)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def wait_for_services(client, app_name, emulator_name, seconds=120):
    deadline = monotonic() + seconds
    emulator_connected = False
    host_error = "unavailable"
    while monotonic() < deadline:
        app, emulator = inspect_container(app_name), inspect_container(emulator_name)
        if app and emulator and app["State"]["Running"] and emulator["State"]["Running"]:
            connection = docker("exec", app_name, "python", "-c", "import socket; socket.create_connection(('firestore',8085),timeout=1).close()", check=False, timeout=5)
            if connection.returncode == 0:
                emulator_connected = True
                try:
                    response = client.get("/health")
                    if response.status_code == 200:
                        return
                    host_error = "HTTP " + str(response.status_code)
                except httpx.HTTPError as exc:
                    host_error = type(exc).__name__
        elif (app and not app["State"]["Running"]) or (emulator and not emulator["State"]["Running"]):
            raise ValidationError("A validation container stopped before becoming ready")
        sleep(1)
    if emulator_connected:
        raise ValidationError("The app connected to the emulator, but localhost app health failed (" + host_error + ")")
    raise ValidationError("The app-to-emulator connection did not become ready")


def wait_after_restart(client, seconds=60):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        try:
            if client.get("/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        sleep(1)
    raise ValidationError("The restarted validation app did not become ready")


def owned_container(name, run_id):
    item = inspect_container(name)
    return bool(item and (item.get("Config", {}).get("Labels") or {}).get(LABEL) == run_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", "--app-image", dest="image", default="ticketpilot-gcp:local")
    parser.add_argument("--emulator-image", default="gcr.io/google.com/cloudsdktool/google-cloud-cli:593.0.0-emulators")
    parser.add_argument("--port", type=int, default=0, help="0 selects a free localhost port")
    args = parser.parse_args(argv)
    if args.port != 0 and not 1024 <= args.port <= 65535:
        parser.error("Choose zero or a nonprivileged localhost port")
    for image in (args.image, args.emulator_image):
        if not image or image.startswith("-") or any(character.isspace() for character in image):
            parser.error("Provide a local Docker image reference")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
        port = probe.getsockname()[1]
    run_id = uuid4().hex
    network = "ticketpilot-gcp-check-" + run_id[:12]
    access_network = network + "-access"
    emulator_name = network + "-firestore"
    app_name = network + "-app"
    local_token = secrets.token_urlsafe(32)
    report = {"scope": "Local disposable Docker app plus real Firestore emulator; fictional records only",
              "container_memory_limit_mib": 512, "container_cpu_limit": 1,
              "root_filesystem": "read-only; temporary /tmp", "cloud_credentials": "not mounted",
              "cloud_account_calls": "none; credential-free local app and emulator only",
              "docker_networking": "internal emulator network; separate app bridge for localhost access"}
    created = []
    passed = False
    try:
        # Avoid implicit registry/network pulls in a purportedly local validation.
        for image in (args.image, args.emulator_image):
            docker("image", "inspect", image, timeout=15)
        docker("network", "create", "--internal", "--label", LABEL + "=" + run_id, network, timeout=30)
        # Docker Desktop cannot reliably publish host ports from an internal-only
        # network. Keep Firestore isolated there, while the app uses its own
        # bridge for the localhost-only published port on both Windows and Linux.
        docker("network", "create", "--label", LABEL + "=" + run_id, access_network, timeout=30)
        docker("run", "--detach", "--pull=never", "--name", emulator_name, "--label", LABEL + "=" + run_id,
               "--network", network, "--network-alias", "firestore", "--memory", "768m", "--cpus", "1",
               "-e", "JAVA_TOOL_OPTIONS=-Xmx512m", "-e", "CLOUDSDK_CORE_DISABLE_PROMPTS=1",
               "-e", "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true", "-e", "CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=true",
               args.emulator_image, "gcloud", "emulators", "firestore", "start", "--host-port=0.0.0.0:8085", "--project=demo-ticketpilot", timeout=30)
        docker("run", "--detach", "--pull=never", "--name", app_name, "--label", LABEL + "=" + run_id,
               "--network", access_network, "--memory", "512m", "--cpus", "1", "--read-only", "--tmpfs", "/tmp:rw,size=64m,mode=1777",
               "-p", "127.0.0.1:" + str(port) + ":8080",
               "-e", "STORAGE_MODE=firestore", "-e", "GOOGLE_CLOUD_PROJECT=demo-ticketpilot",
               "-e", "FIRESTORE_DATABASE=(default)", "-e", "FIRESTORE_EMULATOR_HOST=firestore:8085",
               "-e", "ADMIN_TOKEN=" + local_token, "-e", "METRICS_TOKEN=local-firestore-validation-only",
               "-e", "LLM_PROVIDER=none", "-e", "AWS_EC2_METADATA_DISABLED=true", "-e", "APARTMENT_REFRESH_SECONDS=0",
               "-e", "APARTMENT_QUEUE_LIMIT=20", "-e", "APARTMENT_UNITS=1,2,3,4,5,6,7,8", args.image, timeout=30)
        docker("network", "connect", network, app_name, timeout=30)
        with httpx.Client(base_url="http://127.0.0.1:" + str(port), timeout=30, follow_redirects=False, trust_env=False) as client:
            wait_for_services(client, app_name, emulator_name)
            info = inspect_container(app_name)
            require(info["HostConfig"]["Memory"] == 512 * 1024 * 1024, "App memory limit is not 512 MiB")
            require(info["HostConfig"]["NanoCpus"] == 1000000000 and info["HostConfig"]["ReadonlyRootfs"] is True, "App CPU/root-filesystem limits are not enforced")
            config = client.get("/api/apartments/config").json()
            require(config.get("manager_refresh_seconds") == 0 and config.get("queue_limit") == 20, "Low-read-cost manager settings were not applied")
            report.update(exercise_http(client, local_token, created, "Synthetic local GCP check " + run_id[:12] + ": "))
            # The emulator is isolated, so listing its two fictional concerns is safe.
            queue = client.get("/api/apartments/manage/concerns", headers={"X-Admin-Token": local_token})
            require(queue.status_code == 200, "Local Firestore query failed")
            require({item["id"] for item in queue.json()["items"]} == {item.record_id for item in created}, "Local Firestore query did not isolate concern documents")
            stats = docker("stats", "--no-stream", "--format", "{{json .}}", app_name, check=False, timeout=15)
            if stats.returncode == 0:
                value = json.loads(stats.stdout)
                report["observed_container_memory"] = value.get("MemUsage", "unavailable")
                report["observed_container_cpu_percent"] = value.get("CPUPerc", "unavailable")
            # Only the app process/filesystem is restarted; emulator data remains.
            docker("restart", "--time", "10", app_name, timeout=30)
            wait_after_restart(client)
            for concern in created:
                tracking(client, concern)
            report["firestore_persistence_after_app_restart"] = "passed for both synthetic concerns"
            report["manager_read_cost_settings"] = "manual refresh; queue limited to 20"
            passed = True
    except Exception as exc:
        report.update(failure_details(exc))
        # Only fictional, isolated container logs are written; no host credentials
        # were mounted. Logs are not included in allowlisted CI artifacts.
        ROOT.joinpath(".tools").mkdir(exist_ok=True)
        for name, suffix in ((app_name, "app"), (emulator_name, "emulator")):
            try:
                if owned_container(name, run_id):
                    logs = docker("logs", name, check=False, timeout=15)
                    ROOT.joinpath(".tools/gcp-local-" + suffix + ".log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
            except Exception:
                # Diagnostics must not bypass the safe report and cleanup path.
                report["container_failure_logs"] = "unavailable"
    finally:
        cleanup_errors = []
        for name in (app_name, emulator_name):
            try:
                if owned_container(name, run_id):
                    result = docker("rm", "--force", name, check=False, timeout=30)
                    if result.returncode: cleanup_errors.append("container removal failed")
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        for created_network in (access_network, network):
            try:
                result = docker("network", "inspect", created_network, check=False, timeout=15)
                if result.returncode == 0:
                    data = json.loads(result.stdout)[0]
                    if (data.get("Labels") or {}).get(LABEL) == run_id:
                        result = docker("network", "rm", created_network, check=False, timeout=30)
                        if result.returncode: cleanup_errors.append("network removal failed")
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        report["validation_container_cleanup"] = "failed" if cleanup_errors else "only this run's labeled containers/networks removed"
        if cleanup_errors:
            report["cleanup_error_types"] = cleanup_errors
            passed = False
        report["status"] = "passed" if passed else "failed"
        write_report(ROOT / ".tools/gcp-local-validation.json", report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
