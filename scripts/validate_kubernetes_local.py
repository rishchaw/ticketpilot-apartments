"""Real acceptance of the isolated kind demo; no cloud credentials or calls."""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import kubernetes_local as local
from scripts.validate_gcp_deployment import exercise_http, tracking, require, ValidationError, failure_details

REPORT = ROOT / ".tools/kubernetes-validation.json"


class Forward:
    def __init__(self, commands, service):
        self.commands, self.service = commands, service
        self.process, self.log = None, None

    def start(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.url = "http://127.0.0.1:" + str(port)
        target = local.PORTS[self.service][1]
        self.log = (self.commands.paths.work / ("check-forward-" + self.service + ".log")).open("w", encoding="utf-8")
        command = [self.commands.tools["kubectl"], "--kubeconfig", str(self.commands.paths.kubeconfig),
                   "--context", local.CONTEXT, "--namespace", local.NAMESPACE,
                   "port-forward", "service/" + self.service, f"{port}:{target}", "--address=127.0.0.1"]
        self.process = subprocess.Popen(command, cwd=ROOT, env=self.commands.env(),
                                        stdout=self.log, stderr=self.log,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        path = {"app": "/health", "prometheus": "/-/ready", "grafana": "/api/health"}[self.service]
        deadline = monotonic() + 90
        with httpx.Client(timeout=5, trust_env=False) as client:
            while monotonic() < deadline:
                require(self.process.poll() is None, "A validation port-forward exited")
                try:
                    if client.get(self.url + path).status_code == 200:
                        return self.url
                except httpx.HTTPError:
                    pass
                sleep(1)
        raise ValidationError("A local Kubernetes endpoint did not become ready")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def kubernetes_checks(commands, state):
    for name in ("app", "prometheus", "grafana"):
        commands.kube("rollout", "status", "deployment/" + name, "--timeout=180s", timeout=200)
        deployment = json.loads(commands.kube("get", "deployment", name, "-o", "json").stdout)
        require(deployment["metadata"]["labels"].get(local.OWNER_LABEL) == state["owner"], "Deployment ownership mismatch")
        require(deployment["spec"]["replicas"] == 1 and deployment["status"].get("readyReplicas") == 1, "Deployment is not ready")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        require(pod.get("automountServiceAccountToken") is False, "Workload must not receive an API token")
        require(pod["securityContext"].get("runAsNonRoot") is True, "Workload is not non-root")
        require(container["securityContext"].get("readOnlyRootFilesystem") is True, "Workload root filesystem is writable")
        require(all(key in container for key in ("startupProbe", "readinessProbe", "livenessProbe")), "Workload probes missing")
        require(bool(container["resources"].get("requests")) and bool(container["resources"].get("limits")), "Workload resources missing")
        service = json.loads(commands.kube("get", "service", name, "-o", "json").stdout)
        require(service["spec"]["type"] == "ClusterIP", "Demo service must remain internal")
    app = json.loads(commands.kube("get", "deployment", "app", "-o", "json").stdout)
    require(app["spec"]["strategy"]["type"] == "Recreate", "SQLite workload must use a single-writer deployment strategy")
    require(app["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "512Mi", "App memory limit differs")
    pvc = json.loads(commands.kube("get", "pvc", "app-state", "-o", "json").stdout)
    require(pvc["status"]["phase"] == "Bound" and pvc["spec"]["storageClassName"] == "standard", "Demo PVC is not bound to local storage")
    return {"deployments": "three ready deployments and internal services",
            "workload_controls": "non-root/read-only, probes, resource requests/limits, no API token",
            "sqlite_pvc": "bound local volume; single replica and Recreate strategy"}


def app_pod_uid(commands):
    pods = json.loads(commands.kube("get", "pods", "-l", "app.kubernetes.io/name=app", "-o", "json").stdout)["items"]
    ready = [p for p in pods if not p["metadata"].get("deletionTimestamp") and
             any(c.get("type") == "Ready" and c.get("status") == "True" for c in p["status"].get("conditions", []))]
    require(len(ready) == 1, "Expected one ready application pod")
    return ready[0]["metadata"]["uid"]


def main():
    report = {"scope": "Owned local kind cluster; fictional data; no cloud credentials or account calls"}
    forwards, created = [], []
    passed = False
    try:
        paths = local.DemoPaths(ROOT)
        state = local.load_ownership(paths)
        commands = local.Commands(paths, SimpleNamespace(kind=None, kubectl=None, docker=None))
        local.verify_active(paths, commands, state)
        credentials = json.loads(paths.credentials.read_text(encoding="utf-8"))
        report.update(kubernetes_checks(commands, state))
        endpoints = {}
        for service in ("app", "prometheus", "grafana"):
            forward = Forward(commands, service)
            forwards.append(forward)
            endpoints[service] = forward.start()
        with httpx.Client(base_url=endpoints["app"], timeout=30, trust_env=False, follow_redirects=False) as app:
            report.update(exercise_http(app, credentials["ADMIN_TOKEN"], created,
                                       "Synthetic Kubernetes check " + uuid4().hex[:12] + ": ", expected_storage="sqlite"))
            require(app.get("/metrics").status_code == 401, "Unauthenticated metrics access allowed")
            metrics = app.get("/metrics", headers={"Authorization": "Bearer " + credentials["METRICS_TOKEN"]})
            require(metrics.status_code == 200 and "ticketpilot_apartment_events_total" in metrics.text, "Authenticated metrics failed")
        with httpx.Client(base_url=endpoints["prometheus"], timeout=15, trust_env=False) as prometheus:
            deadline = monotonic() + 75
            up = False
            while monotonic() < deadline:
                response = prometheus.get("/api/v1/query", params={"query": 'up{job="ticketpilot"}'})
                values = response.json().get("data", {}).get("result", [])
                counters = prometheus.get("/api/v1/query", params={"query": "ticketpilot_apartment_events_total"})
                counter_values = counters.json().get("data", {}).get("result", [])
                if response.status_code == 200 and values and values[0]["value"][1] == "1" and counter_values:
                    up = True
                    break
                sleep(2)
            require(up, "In-cluster authenticated scrape and apartment counters did not become healthy")
        report["prometheus"] = "authenticated scrape up; apartment counters queried inside local cluster"
        with httpx.Client(base_url=endpoints["grafana"], auth=("admin", credentials["GRAFANA_ADMIN_PASSWORD"]),
                          timeout=20, trust_env=False) as grafana:
            response = grafana.get("/api/datasources/uid/ticketpilot-prometheus/health")
            require(response.status_code == 200 and response.json().get("status") == "OK", "Grafana datasource health failed")
            for uid, panels in (("ticketpilot-aws", 10), ("ticketpilot-apartments", 6)):
                response = grafana.get("/api/dashboards/uid/" + uid)
                require(response.status_code == 200 and len(response.json()["dashboard"]["panels"]) == panels, "Grafana dashboard provisioning failed")
        report["grafana"] = "Prometheus datasource healthy; both provisioned dashboards verified"
        old_uid = app_pod_uid(commands)
        forwards[0].stop()
        commands.kube("rollout", "restart", "deployment/app")
        commands.kube("rollout", "status", "deployment/app", "--timeout=180s", timeout=200)
        require(app_pod_uid(commands) != old_uid, "Application pod was not replaced")
        app_url = forwards[0].start()
        with httpx.Client(base_url=app_url, timeout=30, trust_env=False) as app:
            for receipt in created:
                tracking(app, receipt)
        report["persistence_after_pod_replacement"] = "both exact synthetic concerns, versions and statuses persisted on PVC"
        report["synthetic_data"] = "two fictional concerns only; removed with the owned disposable cluster by lifecycle cleanup"
        passed = True
    except Exception as error:
        report.update(failure_details(error))
    finally:
        errors = []
        for forward in reversed(forwards):
            try:
                forward.stop()
            except Exception as error:
                errors.append(type(error).__name__)
        report["port_forward_cleanup"] = "passed" if not errors else "failed"
        if errors:
            report["cleanup_error_types"] = errors
            passed = False
        report["status"] = "passed" if passed else "failed"
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
