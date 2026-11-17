"""Isolated, disposable kind portfolio demo. No global kubecontext or cloud resources.

prepare only generates an ignored deployment context and fresh demo credentials.
start builds/loads local images and deploys the demo; stop deletes only its owned
kind cluster, including its fictional SQLite PVC. Real app/cloud records are never mounted.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from urllib.parse import urlparse
from uuid import uuid4

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = "ticketpilot-portfolio"
CONTEXT = "kind-" + CLUSTER
NAMESPACE = "ticketpilot-demo"
OWNER_LABEL = "ticketpilot.local/owner"
PURPOSE_LABEL = "ticketpilot.local/purpose"
PART_OF_LABEL = "app.kubernetes.io/part-of"
APP_IMAGE = "ticketpilot-k8s:local"
NODE_IMAGE = "kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed"
PROMETHEUS_IMAGE = "prom/prometheus:v3.14.0"
GRAFANA_IMAGE = "grafana/grafana:12.1.0"
CREDENTIAL_KEYS = {"ADMIN_TOKEN", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD"}
TEMPLATES = ("kind.yaml", "namespace.yaml", "app-state.yaml", "app.yaml", "prometheus.yaml", "grafana.yaml", "kustomization.yaml")
CONFIG_FILES = {
    "prometheus.yml": "monitoring/prometheus/local.yml",
    "alerts.yml": "monitoring/prometheus/alerts.yml",
    "grafana-datasource.yml": "monitoring/grafana/provisioning/datasources/prometheus.yml",
    "grafana-provider.yml": "monitoring/grafana/provisioning/dashboards/default.yml",
    "apartments.json": "monitoring/grafana/dashboards/apartments.json",
    "ticketpilot.json": "monitoring/grafana/dashboards/ticketpilot.json",
}
PORTS = {"app": (18080, 8080), "prometheus": (19090, 9090), "grafana": (13000, 3000)}


class LocalDemoError(Exception):
    pass


@dataclass(frozen=True)
class DemoPaths:
    root: Path

    @property
    def work(self): return self.root / ".tools" / "kubernetes"
    @property
    def rendered(self): return self.work / "manifests"
    @property
    def kubeconfig(self): return self.work / "kubeconfig"
    @property
    def ownership(self): return self.work / "ownership.json"
    @property
    def credentials(self): return self.root / ".secrets" / "kubernetes-demo.json"


def _safe_path(path: Path, paths: DemoPaths):
    if path.is_symlink():
        raise LocalDemoError("Refusing a symlink at a generated demo path")
    try:
        path.resolve().relative_to(paths.root.resolve())
    except ValueError as exc:
        raise LocalDemoError("Generated demo paths must remain inside this project") from exc


def _write_private(path: Path, value, paths: DemoPaths):
    _safe_path(path, paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2) + "\n"
    temporary = path.with_name(".tmp-" + uuid4().hex[:16])
    _safe_path(temporary, paths)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_ownership(paths: DemoPaths, optional=False):
    _safe_path(paths.ownership, paths)
    if not paths.ownership.exists():
        if optional: return None
        raise LocalDemoError("Run prepare first; no local demo ownership record exists")
    state = json.loads(paths.ownership.read_text(encoding="utf-8"))
    expected = {"schema_version": 1, "cluster_name": CLUSTER, "context": CONTEXT, "namespace": NAMESPACE,
                "workspace": str(paths.root.resolve()), "kubeconfig_path": str(paths.kubeconfig.resolve())}
    if any(state.get(key) != value for key, value in expected.items()):
        raise LocalDemoError("Ownership metadata does not match this workspace/local demo")
    if not re.fullmatch(r"[0-9a-f]{32}", state.get("owner", "")):
        raise LocalDemoError("Invalid local demo owner marker")
    if not isinstance(state.get("node_ids"), list) or any(not re.fullmatch(r"[0-9a-f]{64}", v) for v in state["node_ids"]):
        raise LocalDemoError("Invalid recorded kind node identities")
    return state


def _credentials(paths):
    _safe_path(paths.credentials, paths)
    if paths.credentials.exists():
        value = json.loads(paths.credentials.read_text(encoding="utf-8"))
        if set(value) != CREDENTIAL_KEYS or any(not isinstance(v, str) or len(v) < 32 for v in value.values()):
            raise LocalDemoError("The demo credential file has an unexpected schema; review it before proceeding")
        return value
    value = {key: secrets.token_urlsafe(36) for key in sorted(CREDENTIAL_KEYS)}
    _write_private(paths.credentials, value, paths)
    return value


def prepare(paths: DemoPaths, image=APP_IMAGE):
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]{0,250}", image):
        raise LocalDemoError("Use an explicit local Docker image reference")
    state = load_ownership(paths, optional=True)
    if state is None:
        state = {"schema_version": 1, "cluster_name": CLUSTER, "context": CONTEXT, "namespace": NAMESPACE,
                 "workspace": str(paths.root.resolve()), "kubeconfig_path": str(paths.kubeconfig.resolve()),
                 "owner": uuid4().hex, "node_ids": [], "node_names": [], "phase": "prepared"}
    state.update(app_image=image, node_image=NODE_IMAGE)
    _credentials(paths)  # A new demo-only credential source; never read Compose .env.
    paths.rendered.mkdir(parents=True, exist_ok=True)
    for filename in TEMPLATES:
        source = paths.root / "deploy" / "kubernetes" / filename
        _safe_path(source, paths)
        documents = list(yaml.safe_load_all(source.read_text(encoding="utf-8")))
        for doc in documents:
            if not isinstance(doc, dict):
                raise LocalDemoError("Invalid Kubernetes template")
            if doc.get("kind") == "Cluster":
                nodes = doc.get("nodes", [])
                if len(nodes) != 1 or nodes[0].get("role") != "control-plane" or nodes[0].get("extraMounts") or nodes[0].get("extraPortMappings"):
                    raise LocalDemoError("The demo must use one kind node without host data mounts or service port mappings")
                doc["name"] = CLUSTER
                doc.setdefault("networking", {})["apiServerAddress"] = "127.0.0.1"
                nodes[0].setdefault("labels", {})[OWNER_LABEL] = state["owner"]
            elif doc.get("kind") == "Kustomization":
                doc.setdefault("generatorOptions", {}).setdefault("labels", {})[OWNER_LABEL] = state["owner"]
            else:
                doc.setdefault("metadata", {}).setdefault("labels", {})[OWNER_LABEL] = state["owner"]
                if doc.get("kind") == "Deployment":
                    template = doc["spec"]["template"]
                    template["metadata"]["labels"][OWNER_LABEL] = state["owner"]
                    if doc["metadata"]["name"] == "app": template["spec"]["containers"][0]["image"] = image
        target = paths.rendered / filename
        _safe_path(target, paths)
        target.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
    config = paths.rendered / "config"
    config.mkdir(exist_ok=True)
    for filename, relative in CONFIG_FILES.items():
        source, target = paths.root / relative, config / filename
        _safe_path(source, paths); _safe_path(target, paths)
        shutil.copyfile(source, target)
    _write_private(paths.ownership, state, paths)
    return state


def validate_kubeconfig(paths: DemoPaths):
    _safe_path(paths.kubeconfig, paths)
    if not paths.kubeconfig.is_file():
        raise LocalDemoError("The private kind kubeconfig is not available")
    value = yaml.safe_load(paths.kubeconfig.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("current-context") != CONTEXT:
        raise LocalDemoError("Refusing a kubeconfig that does not select the fixed kind demo context")
    contexts, clusters, users = value.get("contexts", []), value.get("clusters", []), value.get("users", [])
    if len(contexts) != 1 or len(clusters) != 1 or len(users) != 1:
        raise LocalDemoError("The demo kubeconfig must contain only its single local context")
    if contexts[0].get("name") != CONTEXT or contexts[0].get("context", {}).get("cluster") != CONTEXT or contexts[0]["context"].get("user") != CONTEXT:
        raise LocalDemoError("Unexpected kind context mapping")
    cluster, user = clusters[0].get("cluster", {}), users[0].get("user", {})
    endpoint = urlparse(cluster.get("server", ""))
    if clusters[0].get("name") != CONTEXT or users[0].get("name") != CONTEXT or endpoint.scheme != "https" or endpoint.hostname != "127.0.0.1" or not endpoint.port or endpoint.username or endpoint.password or endpoint.path not in ("", "/") or endpoint.query or endpoint.fragment:
        raise LocalDemoError("Refusing a non-loopback Kubernetes API endpoint")
    if cluster.get("proxy-url") or cluster.get("insecure-skip-tls-verify") or not cluster.get("certificate-authority-data"):
        raise LocalDemoError("The local API must use its embedded kind CA without a proxy")
    if set(user) != {"client-certificate-data", "client-key-data"}:
        raise LocalDemoError("Refusing credential plugins, bearer tokens, or external credential files")
    return endpoint


def find_tool(name, explicit, paths):
    candidate = explicit or shutil.which(name)
    if not candidate:
        local = paths.root / ".tools" / (name + (".exe" if os.name == "nt" else ""))
        candidate = str(local) if local.is_file() else None
    if not candidate or not Path(candidate).is_file():
        raise LocalDemoError("Install " + name + " first; this helper never installs tools")
    return str(Path(candidate).resolve())


class Commands:
    def __init__(self, paths, args):
        self.paths = paths
        self.tools = {name: find_tool(name, getattr(args, name, None), paths) for name in ("kind", "kubectl", "docker")}

    def env(self):
        return {**os.environ, "KUBECONFIG": str(self.paths.kubeconfig), "KIND_EXPERIMENTAL_PROVIDER": "docker"}

    def run(self, name, *arguments, input_text=None, check=True, timeout=300):
        command = [self.tools[name], *map(str, arguments)]
        result = subprocess.run(command, cwd=self.paths.root, env=self.env(), input=input_text,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if check and result.returncode:
            raise LocalDemoError(name + " " + str(arguments[0]) + " failed; no credential values were printed")
        return result

    def kube(self, *arguments, input_text=None, check=True, namespace=True, timeout=180):
        validate_kubeconfig(self.paths)
        prefix = ["--kubeconfig", str(self.paths.kubeconfig), "--context", CONTEXT]
        if namespace: prefix += ["--namespace", NAMESPACE]
        return self.run("kubectl", *prefix, *arguments, input_text=input_text, check=check, timeout=timeout)

    def clusters(self):
        return set(self.run("kind", "get", "clusters").stdout.splitlines())

    def nodes(self):
        names = self.run("kind", "get", "nodes", "--name", CLUSTER, check=False).stdout.splitlines()
        if not names: return []
        result = self.run("docker", "inspect", *names)
        nodes = json.loads(result.stdout)
        if any(node.get("Config", {}).get("Labels", {}).get("io.x-k8s.kind.cluster") != CLUSTER for node in nodes):
            raise LocalDemoError("Kind node labels do not match the fixed demo cluster")
        return nodes


def verify_node_ownership(state, nodes):
    current = {node.get("Id") for node in nodes}
    recorded = set(state["node_ids"])
    if not current or not recorded or current != recorded:
        raise LocalDemoError("Refusing an unowned/replaced kind cluster; recorded Docker node IDs must match exactly")
    if any(node.get("Config", {}).get("Labels", {}).get("io.x-k8s.kind.cluster") != CLUSTER for node in nodes):
        raise LocalDemoError("Refusing nodes outside the recorded kind demo")


def verify_namespace(state, document):
    labels = document.get("metadata", {}).get("labels", {})
    if document.get("metadata", {}).get("name") != NAMESPACE or labels.get(OWNER_LABEL) != state["owner"] or labels.get(PURPOSE_LABEL) != "portfolio-demo" or labels.get(PART_OF_LABEL) != "ticketpilot":
        raise LocalDemoError("Refusing a namespace without the matching local-demo ownership labels")


def namespace_document(commands):
    value = commands.kube("get", "namespace", NAMESPACE, "--ignore-not-found", "-o", "json", namespace=False)
    return json.loads(value.stdout) if value.stdout.strip() else None


def verify_active(paths, commands, state):
    nodes = commands.nodes()
    verify_node_ownership(state, nodes)
    endpoint = validate_kubeconfig(paths)
    ports = nodes[0].get("NetworkSettings", {}).get("Ports", {}).get("6443/tcp", [])
    if not any(p.get("HostIp") == "127.0.0.1" and p.get("HostPort") == str(endpoint.port) for p in ports or []):
        raise LocalDemoError("Private kubeconfig endpoint does not match the owned Docker API port")
    namespace = namespace_document(commands)
    if namespace is None: raise LocalDemoError("The owned demo namespace is not available")
    verify_namespace(state, namespace)
    return nodes


@contextmanager
def operation_lock(paths):
    paths.work.mkdir(parents=True, exist_ok=True)
    lock = paths.work / "operation.lock"
    _safe_path(lock, paths)
    marker = uuid4().hex
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise LocalDemoError("Another demo lifecycle operation holds operation.lock; review a stale lock before removing it") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(marker)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        yield
    finally:
        if lock.is_file() and lock.read_text(encoding="utf-8") == marker:
            lock.unlink()


def record_nodes(paths, commands, state):
    nodes = commands.nodes()
    state["node_ids"] = sorted(node["Id"] for node in nodes)
    state["node_names"] = sorted(node["Name"].lstrip("/") for node in nodes)
    _write_private(paths.ownership, state, paths)
    return nodes


def ensure_namespace(commands, state):
    existing = namespace_document(commands)
    if existing is not None:
        verify_namespace(state, existing)
        return
    document = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE,
                "labels": {OWNER_LABEL: state["owner"], PURPOSE_LABEL: "portfolio-demo", PART_OF_LABEL: "ticketpilot",
                           "pod-security.kubernetes.io/enforce": "restricted", "pod-security.kubernetes.io/enforce-version": "latest"}}}
    commands.kube("apply", "-f", "-", input_text=json.dumps(document), namespace=False)


def apply_secret(paths, commands, state):
    values = _credentials(paths)
    document = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque", "metadata": {"name": "ticketpilot-demo-auth", "namespace": NAMESPACE,
                "labels": {OWNER_LABEL: state["owner"], PURPOSE_LABEL: "portfolio-demo", PART_OF_LABEL: "ticketpilot"}},
                "stringData": {**values, "metrics-token": values["METRICS_TOKEN"]}}
    # stdin only: no access code is present in command arguments or tracked YAML.
    commands.kube("apply", "-f", "-", input_text=json.dumps(document))


def safe_creation_diagnostics(result):
    """Only pre-workload kind output; redact bootstrap/authentication material."""
    value = result.stdout + result.stderr
    value = re.sub(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", "[REDACTED PEM]", value, flags=re.DOTALL)
    value = re.sub(r"(?im)^.*(?:client-key-data|client-certificate-data|certificate-authority-data|bootstrapToken|certificate-key).*$",
                   "[REDACTED authentication detail]", value)
    value = re.sub(r"(?i)(--token(?:=|\s+)|token:\s*)[A-Za-z0-9._-]+", r"\1[REDACTED]", value)
    value = re.sub(r"\b[a-z0-9]{6}\\.[a-z0-9]{16}\b", "[REDACTED bootstrap token]", value)
    # Creation precedes app Secret creation; no workload logs or credentials are collected.
    lines = value.splitlines()
    return "\n".join(lines[-100:])


def control_plane_diagnostics(commands, state):
    """Read only owned, pre-workload node diagnostics; never dump manifests/config."""
    try:
        nodes = commands.nodes()
        verify_node_ownership(state, nodes)
        for node in nodes:
            name = node["Name"].lstrip("/")
            journal = commands.run("docker", "exec", name, "journalctl", "--no-pager", "-u", "kubelet", "-n", "60", check=False)
            print("Owned kind node kubelet diagnostics:", file=sys.stderr)
            print(safe_creation_diagnostics(journal), file=sys.stderr)
            for component in ("kube-apiserver", "etcd"):
                result = commands.run("docker", "exec", name, "crictl", "ps", "-a", "--name", component, "-o", "json", check=False)
                containers = json.loads(result.stdout or "{}").get("containers", [])
                if containers:
                    latest = max(containers, key=lambda item: int(item.get("createdAt", 0)))
                    logs = commands.run("docker", "exec", name, "crictl", "logs", "--tail=60", latest["id"], check=False)
                    print("Owned kind " + component + " diagnostics:", file=sys.stderr)
                    print(safe_creation_diagnostics(logs), file=sys.stderr)
    except Exception as error:
        print("Additional control-plane diagnostics unavailable: " + type(error).__name__, file=sys.stderr)


def start(paths, commands, args):
    state = prepare(paths, getattr(args, "image", APP_IMAGE))
    if commands.run("docker", "info", "--format", "{{.OSType}}").stdout.strip() != "linux":
        raise LocalDemoError("The demo requires Docker's Linux container engine")
    existing = CLUSTER in commands.clusters()
    if existing:
        verify_node_ownership(state, commands.nodes())
        if not paths.kubeconfig.is_file():
            commands.run("kind", "export", "kubeconfig", "--name", CLUSTER, "--kubeconfig", str(paths.kubeconfig))
    else:
        state.update(phase="creating", node_ids=[], node_names=[])
        _write_private(paths.ownership, state, paths)
        try:
            created = commands.run("kind", "create", "cluster", "--name", CLUSTER, "--config", str(paths.rendered / "kind.yaml"),
                                   "--kubeconfig", str(paths.kubeconfig), "--image", NODE_IMAGE, "--retain", "--wait", "180s", check=False, timeout=300)
        except BaseException:
            # Retained partial nodes are recorded for a safe stop even if the API never becomes ready.
            state["phase"] = "failed"
            record_nodes(paths, commands, state)
            raise
        record_nodes(paths, commands, state)
        if created.returncode:
            state["phase"] = "failed"
            _write_private(paths.ownership, state, paths)
            print(safe_creation_diagnostics(created), file=sys.stderr)
            control_plane_diagnostics(commands, state)
            raise LocalDemoError("Kind creation failed; recorded demo nodes can be removed with stop")
    try:
        verify_node_ownership(state, commands.nodes())
        validate_kubeconfig(paths)
        paths.kubeconfig.chmod(0o600)
        # Only kind's node-local storage provisioner is accepted; never a cloud storage driver.
        storage = json.loads(commands.kube("get", "storageclass", "standard", "-o", "json", namespace=False).stdout)
        if storage.get("provisioner") != "rancher.io/local-path":
            raise LocalDemoError("Expected kind's standard node-local storage provisioner")
        ensure_namespace(commands, state)
        if not getattr(args, "skip_build", False):
            commands.run("docker", "build", "--file", str(paths.root / "Dockerfile"), "--tag", state["app_image"], str(paths.root), timeout=600)
        for image in (state["app_image"], PROMETHEUS_IMAGE, GRAFANA_IMAGE):
            found = commands.run("docker", "image", "inspect", image, check=False)
            if found.returncode:
                if image == state["app_image"]:
                    raise LocalDemoError("The selected local app image does not exist")
                commands.run("docker", "pull", image, timeout=300)
            commands.run("kind", "load", "docker-image", "--name", CLUSTER, image, timeout=300)
        state["image_id"] = commands.run("docker", "image", "inspect", "--format", "{{.Id}}", state["app_image"]).stdout.strip()
        # Reusing a local tag must still roll out a changed image on repeat starts.
        application = paths.rendered / "app.yaml"
        documents = list(yaml.safe_load_all(application.read_text(encoding="utf-8")))
        for document in documents:
            if document.get("kind") == "Deployment":
                document["spec"]["template"]["metadata"].setdefault("annotations", {})["ticketpilot.local/image-id"] = state["image_id"]
        application.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
        apply_secret(paths, commands, state)
        commands.kube("apply", "-k", str(paths.rendered))
        for deployment in ("app", "prometheus", "grafana"):
            commands.kube("rollout", "status", "deployment/" + deployment, "--timeout=240s", timeout=260)
        state["phase"] = "started"
        _write_private(paths.ownership, state, paths)
        verify_active(paths, commands, state)
        return {"phase": "started", "cluster_name": CLUSTER, "context": CONTEXT, "namespace": NAMESPACE,
                "kubeconfig_path": str(paths.kubeconfig), "credentials_file": str(paths.credentials),
                "note": "Demo credentials were not printed. Use foreground forward commands; stop deletes only this demo cluster and its fictional PVC data."}
    except BaseException:
        state["phase"] = "failed"
        _write_private(paths.ownership, state, paths)
        raise


def stop(paths, commands):
    state = load_ownership(paths, optional=True)
    present = CLUSTER in commands.clusters()
    if not present:
        if state:
            state.update(phase="stopped", node_ids=[], node_names=[])
            _write_private(paths.ownership, state, paths)
        return {"phase": "stopped", "cluster_name": CLUSTER, "note": "No owned demo cluster is running. Real app data was not touched."}
    if state is None:
        raise LocalDemoError("A same-name cluster exists without this project's ownership record; refusing deletion")
    nodes = commands.nodes()
    verify_node_ownership(state, nodes)
    # Active API/namespace labels provide additional protection. A broken/partial
    # cluster can still be cleaned when exact Docker node IDs and kind labels match.
    if paths.kubeconfig.is_file():
        endpoint = validate_kubeconfig(paths)
        published = nodes[0].get("NetworkSettings", {}).get("Ports", {}).get("6443/tcp", []) or []
        if not any(p.get("HostIp") == "127.0.0.1" and p.get("HostPort") == str(endpoint.port) for p in published):
            raise LocalDemoError("Private API endpoint does not match the recorded local kind node")
        existing = commands.kube("get", "namespace", NAMESPACE, "--ignore-not-found", "-o", "json", namespace=False, check=False, timeout=15)
        if existing.returncode == 0 and existing.stdout.strip():
            verify_namespace(state, json.loads(existing.stdout))
    commands.run("kind", "delete", "cluster", "--name", CLUSTER, "--kubeconfig", str(paths.kubeconfig), timeout=180)
    if CLUSTER in commands.clusters():
        raise LocalDemoError("Kind still reports the demo cluster; stop was not confirmed")
    remaining = commands.run("docker", "inspect", *state["node_ids"], check=False)
    if remaining.returncode == 0:
        raise LocalDemoError("Owned node containers still exist; stop was not confirmed")
    state.update(phase="stopped", node_ids=[], node_names=[])
    _write_private(paths.ownership, state, paths)
    return {"phase": "stopped", "cluster_name": CLUSTER,
            "note": "Only the owned kind cluster was deleted. Its fictional SQLite PVC is disposable; real Compose/cloud records and source files remain intact."}


def status(paths, commands):
    state = load_ownership(paths, optional=True)
    if state is None:
        return {"phase": "not_prepared", "cluster_name": CLUSTER}
    if CLUSTER not in commands.clusters():
        return {"phase": "stopped", "cluster_name": CLUSTER, "namespace": NAMESPACE}
    verify_node_ownership(state, commands.nodes())
    if state["phase"] != "started":
        return {"phase": "owned_partial_cluster", "cluster_name": CLUSTER, "recorded_phase": state["phase"], "note": "Use stop to remove these owned demo nodes."}
    verify_active(paths, commands, state)
    deployments = json.loads(commands.kube("get", "deployments", "-o", "json").stdout)
    return {"phase": "started", "cluster_name": CLUSTER, "context": CONTEXT, "namespace": NAMESPACE,
            "deployments": [{"name": d["metadata"]["name"], "ready": d.get("status", {}).get("readyReplicas", 0), "desired": d["spec"]["replicas"]} for d in deployments["items"]],
            "kubeconfig_path": str(paths.kubeconfig), "credentials_file": str(paths.credentials)}


def forward(paths, commands, args):
    state = load_ownership(paths)
    verify_active(paths, commands, state)
    default_port, target = PORTS[args.service]
    port = args.port or default_port
    if not 1024 <= port <= 65535:
        raise LocalDemoError("Use a nonprivileged localhost port")
    command = [commands.tools["kubectl"], "--kubeconfig", str(paths.kubeconfig), "--context", CONTEXT,
               "--namespace", NAMESPACE, "port-forward", "service/" + args.service, f"{port}:{target}", "--address", "127.0.0.1"]
    # Foreground only; never starts a background terminal or changes kubecontext.
    process = subprocess.Popen(command, cwd=paths.root, env=commands.env(),
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=10)
        return 130


def parser():
    common = argparse.ArgumentParser(add_help=False)
    for tool in ("kind", "kubectl", "docker"):
        common.add_argument("--" + tool, default=argparse.SUPPRESS, help="Explicit " + tool + " executable path")
    result = argparse.ArgumentParser(description=__doc__, parents=[common])
    actions = result.add_subparsers(dest="action", required=True)
    for name in ("prepare", "start", "status", "stop", "forward"):
        action = actions.add_parser(name, parents=[common])
        if name in {"prepare", "start"}:
            action.add_argument("--image", default=APP_IMAGE)
        if name == "start": action.add_argument("--skip-build", action="store_true")
        if name == "forward":
            action.add_argument("service", choices=sorted(PORTS))
            action.add_argument("--port", type=int)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    paths = DemoPaths(ROOT.resolve())
    try:
        if args.action == "prepare":
            with operation_lock(paths):
                state = prepare(paths, args.image)
            value = {"phase": "prepared", "cluster_name": CLUSTER, "context": CONTEXT, "namespace": NAMESPACE,
                     "manifest_directory": str(paths.rendered), "kubeconfig_path": str(paths.kubeconfig),
                     "credentials_file": str(paths.credentials), "note": "No tools, images, containers or clusters were installed or started."}
        else:
            commands = Commands(paths, args)
            if args.action == "forward": return forward(paths, commands, args)
            if args.action == "status": value = status(paths, commands)
            else:
                with operation_lock(paths):
                    value = start(paths, commands, args) if args.action == "start" else stop(paths, commands)
        print(json.dumps(value, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Local demo operation interrupted; use status/stop to inspect and clean owned nodes.", file=sys.stderr)
        return 130
    except Exception as error:
        # Avoid dumping YAML/certificate/Secret bodies or credential-bearing command input.
        message = str(error) if isinstance(error, LocalDemoError) else type(error).__name__
        print("Local Kubernetes demo stopped: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
